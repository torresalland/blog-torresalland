import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from . import config, db, security
from .main import app


class BlogAPITest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.original_path=config.DATABASE_PATH
        self.original_hash=config.ADMIN_PASSWORD_HASH
        config.DATABASE_PATH=Path(self.tmp.name)/'blog.sqlite3'
        config.ADMIN_PASSWORD_HASH=security.password_hash('local-test-passphrase-123')
        self.context=TestClient(app)
        self.client=self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None,None,None)
        config.DATABASE_PATH=self.original_path
        config.ADMIN_PASSWORD_HASH=self.original_hash
        self.tmp.cleanup()

    def login(self):
        r=self.client.post('/api/auth/login',json={'username':config.ADMIN_USERNAME,'password':'local-test-passphrase-123'})
        self.assertEqual(r.status_code,200,r.text)
        return {'X-CSRF-Token':r.json()['csrfToken']}

    def payload(self,status='DRAFT'):
        return {'title':'Uma análise técnica original','slug':'uma-analise-tecnica','excerpt':'Um resumo factual.','abstract':'Resumo executivo da análise.','keywords':['IA','Operações'],'tags':['Tecnologia'],'category':'IA aplicada','bodyMarkdown':'## 1 INTRODUÇÃO\n\nTeste de **leitura**.\n\n## 2 CONCLUSÃO\n\nSíntese.','status':status}

    def test_auth_csrf_and_cross_origin(self):
        self.assertEqual(self.client.get('/api/admin/posts').status_code,401)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':config.ADMIN_USERNAME,'password':'wrong'}).status_code,401)
        headers=self.login()
        self.assertEqual(self.client.post('/api/admin/posts',json=self.payload()).status_code,403)
        self.assertEqual(self.client.post('/api/admin/posts',json=self.payload(),headers=headers|{'Origin':'https://attacker.example'}).status_code,403)
        self.assertEqual(self.client.post('/api/admin/posts',json=self.payload(),headers=headers).status_code,200)

    def test_draft_publish_slug_edit_conflict_and_archive(self):
        headers=self.login()
        created=self.client.post('/api/admin/posts',json=self.payload(),headers=headers).json()
        self.assertEqual(self.client.get('/api/posts').json()['posts'],[])
        self.assertEqual(self.client.get('/api/posts/'+created['slug']).status_code,404)
        data=self.payload('PUBLISHED')|{'version':created['version']}
        saved=self.client.put('/api/admin/posts/'+created['id'],json=data,headers=headers).json()
        self.assertEqual(saved['version'],2)
        self.assertEqual(self.client.get('/api/posts/'+created['slug']).status_code,200)
        self.assertEqual(self.client.put('/api/admin/posts/'+created['id'],json=data,headers=headers).status_code,409)
        data=data|{'slug':'slug-atualizado','version':saved['version']}
        updated=self.client.put('/api/admin/posts/'+created['id'],json=data,headers=headers).json()
        self.assertEqual(self.client.get('/api/posts/'+created['slug']).status_code,404)
        self.assertEqual(self.client.get('/api/posts/slug-atualizado').status_code,200)
        revisions=self.client.get('/api/admin/posts/'+created['id']+'/revisions').json()['revisions']
        self.assertEqual(len(revisions),2)
        self.client.put('/api/admin/posts/'+created['id'],json=data|{'status':'ARCHIVED','version':updated['version']},headers=headers)
        self.assertEqual(self.client.get('/api/posts').json()['posts'],[])

    def test_xss_is_not_rendered_and_code_is_highlighted(self):
        headers=self.login()
        markdown='<script>alert(1)</script>\n\n[x](javascript:alert(1))\n\n```python\nprint("hello")\n```\n\n| Campo | Valor |\n|---|---|\n| Teste | Seguro |'
        response=self.client.post('/api/admin/preview',json={'bodyMarkdown':markdown},headers=headers)
        self.assertEqual(response.status_code,200)
        content=response.json()['contentHtml']
        self.assertNotIn('<script>',content)
        self.assertNotIn('href="javascript:',content)
        self.assertIn('<span class=',content)
        self.assertIn('<table>',content)

    def test_settings_and_unique_job_slot(self):
        headers=self.login()
        self.assertEqual(self.client.get('/api/admin/settings').json()['publicationMode'],'PUBLISHED')
        response=self.client.put('/api/admin/settings',json={'publicationMode':'DRAFT','editorialGuidance':'Frases claras.'},headers=headers)
        self.assertEqual(response.json()['publicationMode'],'DRAFT')
        first=db.queue_job({},trigger='SCHEDULE',due_key='2026-10-19/08:30')
        duplicate=db.queue_job({},trigger='SCHEDULE',due_key='2026-10-19/08:30')
        self.assertEqual(first['id'],duplicate['id'])
        self.assertIsNotNone(db.claim_job())
        self.assertIsNone(db.claim_job())

    def test_password_hash_and_logout(self):
        encoded=security.password_hash('one-password')
        self.assertTrue(security.verify_password('one-password',encoded))
        self.assertFalse(security.verify_password('other-password',encoded))
        headers=self.login()
        cookie=self.client.cookies.get(security.COOKIE_NAME)
        with db.connect() as conn:
            session=conn.execute('SELECT * FROM sessions').fetchone()
        self.assertNotEqual(session['token_hash'],cookie)
        self.assertEqual(self.client.post('/api/auth/logout',headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/auth/session').status_code,401)

    def test_login_limit_cannot_be_reset_with_forwarded_ip(self):
        for index in range(8):
            response=self.client.post('/api/auth/login',json={'username':'allan','password':'wrong'},headers={'X-Forwarded-For':f'198.51.100.{index}'})
            self.assertEqual(response.status_code,401)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'allan','password':'wrong'},headers={'X-Forwarded-For':'203.0.113.99'}).status_code,429)

    def test_chunked_request_is_bounded_before_json_parsing(self):
        def oversized():
            yield b'{"username":"'
            for _ in range(60):
                yield b'a'*10000
            yield b'","password":"x"}'
        self.assertEqual(self.client.post('/api/auth/login',content=oversized(),headers={'Content-Type':'application/json'}).status_code,413)

    def test_concurrent_generation_queue_respects_budget(self):
        from concurrent.futures import ThreadPoolExecutor
        def enqueue(_):
            try:
                db.queue_job({},max_pending=5)
                return True
            except db.QueueFull:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(enqueue,range(12)))
        self.assertEqual(sum(results),5)
        self.assertEqual(len(db.list_jobs()),5)

    def test_public_article_with_literal_windows_path_in_title(self):
        headers=self.login()
        payload=self.payload('PUBLISHED')|{'title':r'Configure C:\Users com segurança'}
        created=self.client.post('/api/admin/posts',json=payload,headers=headers).json()
        response=self.client.get('/artigo/'+created['slug']+'/')
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn(r'C:\Users',response.text)

    def test_admin_quick_actions_and_password_change(self):
        headers=self.login()
        created=self.client.post('/api/admin/posts',json=self.payload('DRAFT'),headers=headers).json()
        self.assertEqual(created['status'],'DRAFT')

        # 1-click status change
        published=self.client.post(f'/api/admin/posts/{created["id"]}/status',json={'status':'PUBLISHED'},headers=headers).json()
        self.assertEqual(published['status'],'PUBLISHED')
        self.assertEqual(len(self.client.get('/api/posts').json()['posts']),1)

        draft=self.client.post(f'/api/admin/posts/{created["id"]}/status',json={'status':'DRAFT'},headers=headers).json()
        self.assertEqual(draft['status'],'DRAFT')
        self.assertEqual(len(self.client.get('/api/posts').json()['posts']),0)

        # 1-click delete post
        del_resp=self.client.delete(f'/api/admin/posts/{created["id"]}',headers=headers)
        self.assertEqual(del_resp.status_code,200)
        self.assertEqual(self.client.get(f'/api/admin/posts/{created["id"]}',headers=headers).status_code,404)

        # Legacy and cache-clearing posts.json endpoint
        legacy=self.client.get('/blog/posts.json')
        self.assertEqual(legacy.status_code,200)
        self.assertIn('Clear-Site-Data',legacy.headers)

        # Password change
        pw_resp=self.client.post('/api/admin/password',json={'currentPassword':'local-test-passphrase-123','newPassword':'new-secure-passphrase-999'},headers=headers)
        self.assertEqual(pw_resp.status_code,200)
        # Login with old password fails
        self.assertEqual(self.client.post('/api/auth/login',json={'username':config.ADMIN_USERNAME,'password':'local-test-passphrase-123'}).status_code,401)
        # Login with new password succeeds
        self.assertEqual(self.client.post('/api/auth/login',json={'username':config.ADMIN_USERNAME,'password':'new-secure-passphrase-999'}).status_code,200)


if __name__=='__main__':
    unittest.main()
