import unittest
from unittest.mock import patch

from . import config, monetization

BODY = ''.join(f'<h2>Seção {i}</h2><p>Texto com Notion e notion de novo.</p>' for i in range(4)) + '<h2>REFERÊNCIAS</h2><ul><li>Fonte</li></ul>'
POST = {'title': 'Como vender mais', 'category': 'Negócios', 'tags': ['Vendas'], 'keywords': ['marketing']}
ENTRIES = [{'term': 'Notion', 'url': 'https://exemplo.com/?a=1&b=2', 'store': 'saas'}]


class MonetizationTest(unittest.TestCase):
    def test_cta_off_without_whatsapp(self):
        with patch.object(config, 'YUKI_WHATSAPP', ''):
            self.assertEqual(monetization.inject_cta(BODY, POST), BODY)

    def test_cta_mid_and_end_before_references(self):
        with patch.object(config, 'YUKI_WHATSAPP', '5584999999999'):
            out = monetization.inject_cta(BODY, POST)
        self.assertEqual(out.count('class="cta-box'), 2)
        self.assertLess(out.index('cta-end'), out.index('REFERÊNCIAS'))
        self.assertIn('Tráfego Pago', out)
        self.assertIn('wa.me/5584999999999', out)

    def test_topic_routing(self):
        self.assertEqual(monetization.classify(POST), 'negocios')
        self.assertEqual(monetization.classify({'category': 'IA aplicada', 'tags': ['Automação'], 'keywords': ['n8n']}), 'tecnologia')

    def test_affiliate_first_occurrence_only_outside_headings(self):
        out = monetization.inject_affiliates('<h2>Notion</h2><p>Use Notion e Notion.</p>', ENTRIES)
        self.assertEqual(out.count('<a '), 1)
        self.assertIn('rel="sponsored nofollow noopener"', out)
        self.assertIn('a=1&amp;b=2', out)
        self.assertIn('Divulgação', out)
        self.assertNotIn('<h2><a', out)

    def test_affiliate_skips_existing_links_and_respects_limit(self):
        out = monetization.inject_affiliates('<p><a href="https://x.com">Notion</a></p>', ENTRIES)
        self.assertEqual(out.count('<a '), 1)
        many = [{'term': t, 'url': 'https://e.com/' + t, 'store': ''} for t in ('Alfa', 'Beta', 'Gama', 'Delta')]
        out = monetization.inject_affiliates('<p>Alfa Beta Gama Delta</p>', many, limit=3)
        self.assertEqual(out.count('class="affiliate-link"'), 3)

    def test_monetize_never_raises(self):
        with patch.object(monetization, 'inject_cta', side_effect=RuntimeError):
            self.assertEqual(monetization.monetize(BODY, POST), BODY)


if __name__ == '__main__':
    unittest.main()
