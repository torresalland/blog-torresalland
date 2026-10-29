"""Offline tests: transport boundaries, collection, evidence gates and job recovery."""
import copy
import hashlib
import socket
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from . import config, db, editorial, generator, sources, worker


def dns_answer(host,port,**kwargs):
    try:
        socket.inet_pton(socket.AF_INET,host)
        ip = host
    except OSError:
        ip = '93.184.216.34'
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,port))]


def sample_corpus():
    date = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return [
        {'id':'item1','referenceId':'S1','source_id':'openai','title':'Documento da instituição','url':'https://openai.com/news/documento','author':'OpenAI','publisher':'OpenAI','published_at':date,'accessed_at':date,'primary':True,'pillar':'IA','content':' '.join(f'evidencia{x}' for x in range(220))},
        {'id':'item2','referenceId':'S2','source_id':'siscomex','title':'Operações de comércio exterior','url':'https://www.gov.br/siscomex/noticia','author':'Siscomex','publisher':'Siscomex','published_at':date,'accessed_at':date,'primary':True,'pillar':'Comércio Exterior','content':' '.join(f'fonte{x}' for x in range(220))},
    ]


def sample_article(corpus=None):
    corpus = corpus or sample_corpus()
    body = '\n\n'.join(f'## {section} ANÁLISE\n\n'+' '.join(f'argumento{section}_{word}' for word in range(240)) for section in range(1,4))
    body += '\n\n'+' '.join(editorial.citation_label(source) for source in corpus)
    return {'title':'IA e documentos em operações internacionais','slug':'ia-documentos-operacoes','excerpt':'Análise das escolhas de automação documental.','abstract':' '.join(f'resumo{x}' for x in range(80)),'keywords':['IA','Automação','Comércio Exterior'],'tags':['Análise'],'category':'IA','bodyMarkdown':body,'referenceIds':['S1','S2']}


def sample_review():
    return {'approved':True,'issues':[],'unsupportedClaims':[],'legalPrimaryVerified':False,'pillarCount':5,'evidenceReferenceIds':['S1','S2']}


class DatabaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config_patch = patch.object(config,'DATABASE_PATH',Path(self.temp.name)/'test.sqlite3')
        self.config_patch.start()
        db.init()

    def tearDown(self):
        self.config_patch.stop()
        self.temp.cleanup()


class PublicSourceTests(DatabaseTest):
    @patch.object(socket,'getaddrinfo',side_effect=dns_answer)
    def test_ssrf_rejects_private_credentials_ports_and_mixed_dns(self,_dns):
        blocked = ['http://127.0.0.1/a','http://169.254.169.254/latest/meta-data','http://10.0.0.1','http://192.168.2.1','file:///etc/passwd','https://user:password@example.com/a','https://example.com:9000/a','http://example.local/a','https://example.com/\nHost:localhost','https://example.com\\@localhost/']
        for url in blocked:
            with self.subTest(url=url), self.assertRaises(sources.SourceError):
                sources.validate_url(url)
        self.assertEqual(sources.validate_url('https://example.com/a#b'),'https://example.com/a')
        public = dns_answer('example.com',443)
        private = dns_answer('127.0.0.1',443)
        with patch.object(socket,'getaddrinfo',return_value=public+private):
            with self.assertRaises(sources.SourceError):
                sources.validate_url('https://example.com')

    def test_ipv6_multicast_and_embedded_loopback_are_rejected(self):
        for ip in ('::1','::ffff:127.0.0.1','ff0e::1','2002:7f00:0001::'):
            with self.subTest(ip=ip),patch.object(socket,'getaddrinfo',return_value=[(socket.AF_INET6,socket.SOCK_STREAM,6,'',(ip,443,0,0))]), self.assertRaises(sources.SourceError):
                sources.validate_url('https://public.example')

    @patch.object(socket,'getaddrinfo',side_effect=dns_answer)
    def test_redirect_to_metadata_is_blocked_before_following(self,_dns):
        client = Mock()
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        client.get.return_value = httpx.Response(302,headers={'location':'http://169.254.169.254/latest/meta-data'})
        with patch.object(httpx,'Client',return_value=client),self.assertRaises(sources.SourceError):
            sources.fetch_public('https://example.com/feed')
        self.assertEqual(client.get.call_count,1)

    @patch.object(socket,'getaddrinfo',side_effect=dns_answer)
    def test_pinned_connection_gets_checked_ip_and_oversize_is_blocked(self,_dns):
        connection = Mock()
        response = connection.getresponse.return_value
        response.getheader.side_effect = lambda name,default=None: str(sources.MAX_BYTES+1) if name == 'Content-Length' else default
        with patch.object(sources,'_PinnedHTTPS',return_value=connection) as pinned,self.assertRaises(sources.SourceError):
            sources.PublicTransport().handle_request(httpx.Request('GET','https://example.com/article'))
        self.assertEqual(pinned.call_args.args[:2],('example.com','93.184.216.34'))
        connection.close.assert_called_once()

    def test_rss_collection_normalizes_tracking_and_deduplicates(self):
        rss = b'''<rss version="2.0"><channel><title>Public source</title><item><title>A real title</title><link>https://example.com/news/?utm_source=test</link><pubDate>Mon, 19 Oct 2026 12:00:00 GMT</pubDate><description>Summary</description></item><item><title>Same article</title><link>https://example.com/news</link></item></channel></rss>'''
        response = httpx.Response(200,content=rss,headers={'content-type':'application/rss+xml'})
        source = {'id':'fixture','url':'https://example.com/rss','kind':'feed'}
        with patch.object(sources,'fetch_public',return_value=(response,source['url'])):
            sources.collect_source(source)
            sources.collect_source(source)
        with db.connect() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM feed_items').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT status FROM source_health').fetchone()[0],'OK')

    def test_article_requires_real_date_and_never_launders_primary_identity(self):
        text = ' '.join(f'documento{x}' for x in range(210))
        html = '<html><h1>Título real</h1><article>'+text+'</article></html>'
        response = httpx.Response(200,text=html,headers={'content-type':'text/html'})
        item = {'source_id':'openai','url':'https://openai.com/news/original','title':'Feed title','published_at':None}
        with patch.object(sources,'fetch_public',return_value=(response,'https://unrelated.example/article')):
            with self.assertRaises(sources.SourceError):
                sources.read_article(item)
            item['published_at'] = '2026-01-01T12:00:00+00:00'
            article = sources.read_article(item)
        self.assertFalse(article['primary'])
        self.assertEqual(article['publisher'],'unrelated.example')
        self.assertEqual(article['title'],'Título real')

    def test_blocked_feed_becomes_explicit_health_error(self):
        with patch.object(sources,'fetch_public',side_effect=sources.SourceError('Fonte retornou HTTP 403; acesso não contornado.')):
            self.assertEqual(sources.collect_source({'id':'blocked','url':'https://example.com','kind':'html'}),0)
        with db.connect() as conn:
            row = conn.execute('SELECT * FROM source_health').fetchone()
        self.assertEqual(row['status'],'ERROR')
        self.assertIn('403',row['error'])

    def test_exact_twenty_three_sources_are_configured(self):
        self.assertEqual(len(sources.FEEDS),23)
        self.assertEqual(len({source['id'] for source in sources.FEEDS}),23)
        self.assertEqual(sum(source['kind']=='html' for source in sources.FEEDS),5)


class EditorialTests(DatabaseTest):
    def test_complete_supported_article_passes_and_references_are_deterministic(self):
        corpus = sample_corpus()
        article = sample_article(corpus)
        self.assertEqual(editorial.quality_issues(article,corpus,sample_review()),[])
        references = editorial.reference_records(article,corpus)
        references[0]['accessedAt'] = '2026-10-20T12:00:00+00:00'
        output = editorial.append_references(article['bodyMarkdown'],references)
        self.assertIn('## REFERÊNCIAS',output)
        self.assertIn('Acesso em: 20 out. 2026.',output)
        self.assertNotIn('Head of Legal',output)
        self.assertEqual(editorial.append_references(article['bodyMarkdown'],references),output)

    def test_unsupported_review_and_fabricated_sources_fail(self):
        corpus = sample_corpus()
        article = sample_article(corpus)
        review = sample_review() | {'approved':False,'unsupportedClaims':['Benefício não demonstrado.']}
        self.assertTrue(editorial.quality_issues(article,corpus,review))
        article['referenceIds'] = ['S1','inventada']
        self.assertTrue(editorial.quality_issues(article,corpus,sample_review()))

    def test_specific_legal_claim_needs_primary_evidence(self):
        corpus = sample_corpus()
        article = sample_article(corpus)
        article['bodyMarkdown'] += '\nA Lei 12345 permite a atividade.'
        self.assertTrue(any('normativa' in issue for issue in editorial.quality_issues(article,corpus,sample_review())))

    def test_extended_source_copy_is_rejected(self):
        corpus = sample_corpus()
        article = sample_article(corpus)
        article['bodyMarkdown'] += '\n'+corpus[0]['content']
        self.assertTrue(any('Sobreposição' in issue for issue in editorial.quality_issues(article,corpus,sample_review())))

    def test_code_examples_are_preserved_but_raw_scripts_fail(self):
        corpus = sample_corpus()
        article = sample_article(corpus)
        article['bodyMarkdown'] += '\n```python\nprint("Exemplo didático")\n```\n'
        article['bodyMarkdown'] += '\n```javascript\nconst endpoint = "https://example.com/api";\n```\n'
        article['bodyMarkdown'] += '\n```html\n<script>console.log("Demonstração sem execução")</script>\n```\n'
        self.assertEqual(editorial.quality_issues(article,corpus,sample_review()),[])
        article['bodyMarkdown'] += '<script>alert(1)</script>'
        self.assertTrue(editorial.quality_issues(article,corpus,sample_review()))

    def test_five_lenses_required_and_numbered_headings_are_normalized(self):
        corpus = sample_corpus()
        article = sample_article(corpus)
        self.assertTrue(editorial.quality_issues(article,corpus,sample_review()|{'pillarCount':3}))
        dotted = article['bodyMarkdown'].replace('## 1 ANÁLISE','## 1. ANÁLISE')
        article['bodyMarkdown'] = editorial.normalize_headings(dotted)
        self.assertEqual(editorial.quality_issues(article,corpus,sample_review()),[])

    def test_generator_runs_generation_and_independent_review_before_output(self):
        corpus = sample_corpus()
        article = sample_article(corpus)
        with patch.object(generator,'select_corpus',return_value=corpus),patch.object(generator,'llm_json',side_effect=[article,sample_review()]) as llm:
            result = generator.generate_article({'id':'generation','payload':{}})
        self.assertEqual(llm.call_count,2)
        self.assertTrue(llm.call_args.kwargs['review'])
        self.assertEqual(result['status'],'PUBLISHED')
        self.assertEqual(len(result['references']),2)
        self.assertEqual(result['_sourceItemIds'],['item1','item2'])

    def test_rejected_generation_never_persists_post(self):
        corpus = sample_corpus()
        with patch.object(generator,'select_corpus',return_value=corpus),patch.object(generator,'llm_json',side_effect=[sample_article(corpus),sample_review()|{'approved':False}]):
            with self.assertRaises(editorial.QualityError):
                generator.generate_article({'id':'bad-generation','payload':{}})
        self.assertEqual(db.list_posts(),[])


class SchedulerAndRecoveryTests(DatabaseTest):
    def test_brasilia_slots_have_persistent_idempotent_keys(self):
        settings = db.get_settings() | {'schedulerEnabled':True}
        before = datetime(2026,10,20,11,29,tzinfo=timezone.utc)
        self.assertEqual(worker.schedule_due(settings,before),[])
        morning = datetime(2026,10,20,11,30,tzinfo=timezone.utc)
        first = worker.schedule_due(settings,morning)
        again = worker.schedule_due(settings,morning+timedelta(minutes=3))
        self.assertEqual(first[0]['id'],again[0]['id'])
        worker.schedule_due(settings,datetime(2026,10,20,21,30,tzinfo=timezone.utc))
        worker.schedule_due(settings,datetime(2026,10,20,23,0,tzinfo=timezone.utc))
        self.assertEqual(len(db.list_jobs()),2)
        self.assertTrue(all('America/Sao_Paulo/2026-10-20/' in job['due_key'] for job in db.list_jobs()))
        self.assertEqual(worker.schedule_due(settings|{'schedulerEnabled':False},morning),[])

    def test_claim_serializes_jobs_and_stale_work_is_recovered(self):
        one,two = db.queue_job({}),db.queue_job({})
        claimed = db.claim_job()
        self.assertEqual(claimed['id'],one['id'])
        self.assertIsNone(db.claim_job())
        old = (datetime.now(timezone.utc)-timedelta(minutes=25)).isoformat()
        with db.connect() as conn:
            conn.execute('UPDATE jobs SET heartbeat_at=? WHERE id=?',(old,one['id']))
        recovered = db.claim_job()
        self.assertEqual(recovered['id'],one['id'])
        self.assertEqual(recovered['attempt'],2)
        db.finish_job(one['id'],error='Interrupted')
        self.assertEqual(db.claim_job()['id'],two['id'])

    def test_crash_after_save_reuses_persisted_generation_without_model_call(self):
        job = db.queue_job({})
        db.claim_job()
        article = sample_article() | {'status':'PUBLISHED'}
        persisted = db.save_post(article,generation_id=job['id'])
        with patch.object(generator,'generate_article') as generate:
            resumed = worker.run_job(db.get_job(job['id']))
        generate.assert_not_called()
        self.assertEqual(resumed['id'],persisted['id'])
        self.assertEqual(len(db.list_posts(public=True)),1)
        self.assertEqual(db.get_job(job['id'])['status'],'SUCCEEDED')

    def test_quality_failure_and_latest_draft_setting_cannot_publish(self):
        job = db.queue_job({})
        with patch.object(generator,'generate_article',side_effect=editorial.QualityError('Sem evidência.')):
            self.assertIsNone(worker.run_job(job))
        self.assertEqual(db.get_job(job['id'])['status'],'FAILED')
        self.assertEqual(db.list_posts(public=True),[])
        db.update_settings({'publicationMode':'DRAFT'})
        job2 = db.queue_job({})
        with patch.object(generator,'generate_article',return_value=sample_article()|{'status':'PUBLISHED'}):
            post = worker.run_job(job2)
        self.assertEqual(post['status'],'DRAFT')
        self.assertEqual(db.list_posts(public=True),[])

    def test_heartbeat_updates_during_long_generation(self):
        job = db.queue_job({})
        def delayed(_job):
            time.sleep(0.08)
            return sample_article() | {'status':'DRAFT'}
        with patch.object(worker,'HEARTBEAT_SECONDS',0.01),patch.object(generator,'generate_article',side_effect=delayed),patch.object(db,'job_heartbeat',wraps=db.job_heartbeat) as beat:
            worker.run_job(job)
        self.assertGreaterEqual(beat.call_count,1)
        self.assertTrue(db.get_settings()['worker']['heartbeat_at'])


if __name__ == '__main__':
    unittest.main()
