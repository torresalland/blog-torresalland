"""Evidence-led generation and a separate factual-review model call."""
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx

from . import db, editorial, sources


def llm_json(system, payload, review=False):
    provider = os.environ.get('LLM_PROVIDER','gemini').lower()
    defaults = {'gemini':'gemini-3-flash-preview','openai':'gpt-4.1-mini','anthropic':'claude-sonnet-4-20250514'}
    model = os.environ.get('LLM_MODEL') or defaults.get(provider)
    key_name = {'gemini':'GEMINI_API_KEY','openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY'}.get(provider)
    key = os.environ.get(key_name,'') if key_name else ''
    if not model or not key:
        raise editorial.QualityError('Provedor de IA não configurado; nenhuma publicação foi feita.')
    prompt = json.dumps(payload,ensure_ascii=False)
    max_tokens = 8192 if review else 16384
    headers = {'Content-Type':'application/json'}
    if provider == 'gemini':
        if not re.fullmatch(r'[A-Za-z0-9._-]+',model):
            raise editorial.QualityError('Nome de modelo inválido.')
        candidate_models = list(dict.fromkeys([model,'gemini-3-flash-preview','gemini-3.6-flash','gemini-3.8-flash','gemini-3.7-flash','gemini-3.5-flash','gemini-3.1-flash-lite']))
        candidate_keys = [k for k in dict.fromkeys([key, os.environ.get('GEMINI_API_KEY_FALLBACK','')]) if k]
        last_status = None
        try:
            with httpx.Client(timeout=httpx.Timeout(180,connect=20),trust_env=False) as client:
                for cand_model in candidate_models:
                    endpoint = f'https://generativelanguage.googleapis.com/v1beta/models/{cand_model}:generateContent'
                    body = {'systemInstruction':{'parts':[{'text':system}]},'contents':[{'role':'user','parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.15 if review else 0.35,'maxOutputTokens':max_tokens,'responseMimeType':'application/json'}}
                    for cand_key in candidate_keys:
                        req_headers = dict(headers, **{'x-goog-api-key': cand_key})
                        for attempt in range(2):
                            try:
                                response = client.post(endpoint,headers=req_headers,json=body)
                            except httpx.HTTPError:
                                if attempt == 0:
                                    time.sleep(2)
                                    continue
                                response = None
                                break
                            last_status = response.status_code
                            if response.status_code not in (429,500,502,503,504) or attempt == 1:
                                break
                            time.sleep(2 ** (attempt+1))
                        if response is not None and response.status_code < 400:
                            try:
                                data = response.json()
                                parts = data['candidates'][0]['content']['parts']
                                non_thought = [part.get('text','') for part in parts if not part.get('thought')]
                                text = ''.join(non_thought if any(non_thought) else [part.get('text','') for part in parts])
                                text = re.sub(r'^```(?:json)?\s*|\s*```$', '',text.strip())
                                result = json.loads(text)
                                if isinstance(result,dict):
                                    return result
                            except (ValueError, KeyError, IndexError, TypeError):
                                pass
                        if response is not None and response.status_code not in (404,429,500,502,503,504):
                            break
            if last_status and last_status >= 400:
                raise editorial.QualityError(f'Provedor de IA retornou HTTP {last_status}; nenhuma publicação foi feita.')
            raise editorial.QualityError('Resposta inválida ou indisponibilidade do provedor de IA; nenhuma publicação foi feita.')
        except editorial.QualityError:
            raise
        except Exception as exc:
            raise editorial.QualityError('Resposta inválida ou indisponibilidade do provedor de IA; nenhuma publicação foi feita.') from exc
    elif provider == 'openai':
        endpoint = 'https://api.openai.com/v1/chat/completions'
        headers['Authorization'] = 'Bearer ' + key
        body = {'model':model,'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],'response_format':{'type':'json_object'},'temperature':0.15 if review else 0.35,'max_tokens':max_tokens}
    else:
        endpoint = 'https://api.anthropic.com/v1/messages'
        headers.update({'x-api-key':key,'anthropic-version':'2023-06-01'})
        body = {'model':model,'system':system,'messages':[{'role':'user','content':prompt}],'temperature':0.15 if review else 0.35,'max_tokens':max_tokens}
    try:
        with httpx.Client(timeout=httpx.Timeout(180,connect=20),trust_env=False) as client:
            for attempt in range(3):
                response = client.post(endpoint,headers=headers,json=body)
                if response.status_code not in (429,500,502,503,504) or attempt == 2:
                    break
                time.sleep(2 ** (attempt+1))
        if response.status_code >= 400:
            raise editorial.QualityError(f'Provedor de IA retornou HTTP {response.status_code}; nenhuma publicação foi feita.')
        data = response.json()
        if provider == 'openai':
            text = data['choices'][0]['message']['content']
        else:
            text = ''.join(part.get('text','') for part in data['content'] if part.get('type') == 'text')
        text = re.sub(r'^```(?:json)?\s*|\s*```$', '',text.strip())
        result = json.loads(text)
        if not isinstance(result,dict):
            raise ValueError('object required')
        return result
    except editorial.QualityError:
        raise
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise editorial.QualityError('Resposta inválida ou indisponibilidade do provedor de IA; nenhuma publicação foi feita.') from exc


def select_corpus(payload):
    with db.connect() as conn:
        recent_check = conn.execute("SELECT MAX(checked_at) FROM source_health").fetchone()[0]
    if not recent_check or (datetime.now(timezone.utc) - datetime.fromisoformat(recent_check)) > timedelta(minutes=20):
        sources.collect_all()
    with db.connect() as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM feed_items WHERE status='NEW' ORDER BY COALESCE(published_at,seen_at) DESC LIMIT 240")]
    def folded(text):
        return unicodedata.normalize('NFKD',text).encode('ascii','ignore').decode().lower()
    topic = folded(payload.get('topic',''))
    terms = {word for word in re.findall(r'\w+',topic) if len(word) > 3}
    groups = []
    if not topic or any(word in topic for word in ('document','audit','ocr','conform','governan')):
        groups.append((3,('documento','documental','paperwork','ocr','audit','compliance','conformidade','evaluation','fairness','governance','governanca')))
    if not topic or any(word in topic for word in ('comerc','comex','exterior','internacion','trade','export','import','supply')):
        groups.append((2,('comex','comercio','exterior','internacion','export','importa','trade','customs','fronteira','wto','supply chain','licensing')))
    if not topic or re.search(r'\b(?:ia|ai|inteligencia|llm)\b',topic):
        groups.append((1,('inteligencia artificial','artificial intelligence','language model',' ai ',' llm','agente','agent','model')))
    noise_terms = ('currentscript','moraes','mendonca','pgr ','ebola','midterms','obituary','0.1','0.5','confectionary','mogadishu','meth','seizes','cocaine','fentanyl','narcotics')
    now = datetime.now(timezone.utc)
    def score(row):
        date = sources.normalize_date(row.get('published_at'))
        age = (now-datetime.fromisoformat(date)).total_seconds()/86400 if date else 3
        title,summary = folded(row['title']),folded(row['summary'])
        if any(bad in title for bad in noise_terms):
            return -100
        relevance = sum(6 if term in title else 2 if term in summary else 0 for term in terms)
        relevance += sum(weight*(8 if any(term in title for term in synonyms) else 3 if any(term in summary for term in synonyms) else 0) for weight,synonyms in groups)
        primary = sources.SOURCE_MAP.get(row['source_id'],{}).get('primary',False)
        institutional = any(h in row.get('url','') for h in ('wto.org','gov.br','jus.br'))
        return relevance + (6 if primary else 0) + (5 if institutional else 0) - min(age,100)
    rows.sort(key=score,reverse=True)
    corpus, hosts, pillars = [], set(), set()
    if payload.get('url'):
        url = sources.validate_url(payload['url'])
        matching = next((row for row in rows if row['url'].rstrip('/') == url.rstrip('/')),None)
        matched_source = next((source for source in sources.FEEDS if urlsplit(source['url']).hostname == urlsplit(url).hostname),None)
        item = matching or {'source_id':matched_source['id'] if matched_source else 'manual','url':url,'title':topic or urlsplit(url).hostname,'published_at':None}
        article = sources.read_article(item)
        corpus.append(article)
        hosts.add(urlsplit(article['url']).hostname.removeprefix('www.'))
        pillars.add(article['pillar'])
    # Prefer independent domains, primary institutional evidence, and diverse lenses.
    candidates = rows[:50]
    attempts = 0
    host_failures = {}
    while candidates and len(corpus) < 5 and attempts < 18:
        has_primary = sum(1 for c in corpus if c.get('primary'))
        candidates.sort(key=lambda row: score(row) + (5 if sources.SOURCE_MAP.get(row['source_id'],{}).get('pillar') not in pillars else 0) + (8 if has_primary < 2 and sources.SOURCE_MAP.get(row['source_id'],{}).get('primary') else 0),reverse=True)
        item = candidates.pop(0)
        host = urlsplit(item['url']).hostname.removeprefix('www.')
        if host in hosts or host_failures.get(host,0) >= 2:
            continue
        date = sources.normalize_date(item.get('published_at'))
        if date and now-datetime.fromisoformat(date) > timedelta(days=14):
            continue
        attempts += 1
        try:
            article = sources.read_article(item)
            if now-datetime.fromisoformat(article['published_at']) > timedelta(days=14):
                continue
            final_host = urlsplit(article['url']).hostname.removeprefix('www.')
            if final_host in hosts:
                continue
            corpus.append(article)
            hosts.add(final_host)
            pillars.add(article['pillar'])
        except sources.SourceError as exc:
            host_failures[host] = host_failures.get(host,0) + 1
            db.event('source.article_unavailable', {'source':item['source_id'],'reason':str(exc)[:200]})
    if len(corpus) < 2 or len(hosts) < 2 or not any(item.get('primary') for item in corpus):
        raise editorial.QualityError('Não há duas fontes atuais e independentes efetivamente lidas, incluindo uma primária. Tente outra pauta ou aguarde novas fontes.')
    for number, item in enumerate(corpus,1):
        item['referenceId'] = f'S{number}'
    return corpus


def generate_article(job: dict) -> dict:
    payload = job.get('payload',{})
    settings = db.get_settings()
    corpus = select_corpus(payload)
    evidence = [{key:item[key] for key in ('referenceId','title','url','author','publisher','published_at','accessed_at','primary','pillar','content')} for item in corpus]
    for item in evidence:
        item['expectedCitation'] = editorial.citation_label(item)
    request = {'dateUTC':db.now(),'topic':payload.get('topic',''),'sources':evidence,'editorialGuidance':settings.get('editorialGuidance','')[:10000],'humanEditedStyleExamples':editorial.adaptation_examples(),'internalArticles':editorial.internal_articles()}
    article = llm_json(editorial.SYSTEM_PROMPT,request)
    if isinstance(article.get('bodyMarkdown'),str):
        article['bodyMarkdown'] = editorial.normalize_headings(article['bodyMarkdown'])
    review = llm_json(editorial.REVIEW_PROMPT,{'sources':evidence,'article':article},review=True)
    issues = editorial.quality_issues(article,corpus,review)
    with db.connect() as conn:
        previous = [dict(row) for row in conn.execute('SELECT title,body_markdown FROM posts ORDER BY created_at DESC LIMIT 40')]
    for older in previous:
        if editorial.copied_span(article.get('bodyMarkdown',''),older['body_markdown'],minimum=45):
            issues.append('Artigo repete trecho extenso de publicação anterior.')
            break
        if editorial.slugify(article.get('title','')) == editorial.slugify(older['title']):
            issues.append('Pauta duplica título de artigo existente.')
            break
    if issues:
        try:
            correction_req = dict(request, previousDraft=article, validationIssues=issues[:10], reviewerFeedback=review.get('issues',[])[:8] + review.get('unsupportedClaims',[])[:8], instruction='Corrija integralmente todos os apontamentos em validationIssues e reviewerFeedback mantendo rigorosamente as citações expectedCitation no corpo, extensão entre 750 e 1350 palavras, H2 numerados sequencialmente (## 1 ..., ## 2 ..., ## 3 ...) e os 5 eixos editoriais.')
            article_retry = llm_json(editorial.SYSTEM_PROMPT, correction_req)
            if isinstance(article_retry.get('bodyMarkdown'),str):
                article_retry['bodyMarkdown'] = editorial.normalize_headings(article_retry['bodyMarkdown'])
            review_retry = llm_json(editorial.REVIEW_PROMPT, {'sources':evidence,'article':article_retry}, review=True)
            issues_retry = editorial.quality_issues(article_retry, corpus, review_retry)
            for older in previous:
                if editorial.copied_span(article_retry.get('bodyMarkdown',''),older['body_markdown'],minimum=45):
                    issues_retry.append('Artigo repete trecho extenso de publicação anterior.')
                    break
                if editorial.slugify(article_retry.get('title','')) == editorial.slugify(older['title']):
                    issues_retry.append('Pauta duplica título de artigo existente.')
                    break
            if not issues_retry:
                article, review, issues = article_retry, review_retry, issues_retry
            else:
                issues = issues_retry
                review = review_retry
        except (editorial.QualityError, StopIteration, RuntimeError):
            pass
    if issues:
        db.event('generation.rejected',{'job':job.get('id'),'issues':issues[:12],'reviewIssues':review.get('issues',[])[:8]})
        raise editorial.QualityError('Rascunho reprovado: ' + ' '.join(issues[:5]))
    article['slug'] = editorial.slugify(article.get('slug') or article['title'])
    if not article['slug']:
        raise editorial.QualityError('Slug de artigo inválido.')
    references = editorial.reference_records(article,corpus)
    article['references'] = references
    article['bodyMarkdown'] = editorial.append_references(article['bodyMarkdown'],references)
    article['category'] = article.get('category') if article.get('category') in ('Direito','IA','Inteligência Artificial','Automação','Comércio Exterior','Estratégia','Análise') else 'Análise'
    article['status'] = settings.get('publicationMode','DRAFT')
    article['_sourceItemIds'] = [item['id'] for item in corpus if item.get('id') and item['referenceId'] in article['referenceIds']]
    return article
