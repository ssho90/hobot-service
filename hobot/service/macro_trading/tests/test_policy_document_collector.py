import unittest
from datetime import datetime

from service.macro_trading.collectors.policy_document_collector import (
    PolicyDocumentCollector,
    PolicyFeedSource,
)


class TestPolicyDocumentCollector(unittest.TestCase):
    def test_parse_feed_entries_rss(self):
        collector = PolicyDocumentCollector()
        xml = """
        <rss version="2.0">
          <channel>
            <item>
              <title>FOMC statement</title>
              <link>https://example.com/fomc</link>
              <description>Policy decision details</description>
              <pubDate>Tue, 18 Feb 2026 18:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>
        """
        rows = collector.parse_feed_entries(xml)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "FOMC statement")
        self.assertEqual(rows[0]["link"], "https://example.com/fomc")
        self.assertIsInstance(rows[0]["published_at"], datetime)

    def test_build_document_row_enforces_temporal_fields(self):
        source = PolicyFeedSource(
            key="fed_policy",
            name="Fed policy",
            country="United States",
            country_ko="미국",
            category="Monetary Policy",
            category_ko="통화정책",
            feed_url="https://example.com/rss.xml",
        )
        observed_at = datetime(2026, 2, 18, 12, 0, 0)
        row = PolicyDocumentCollector.build_document_row(
            {
                "title": "Policy update",
                "link": "https://example.com/policy",
                "description": "desc",
                "published_at": datetime(2026, 2, 18, 9, 0, 0),
            },
            source,
            observed_at=observed_at,
        )
        self.assertEqual(row["release_date"], datetime(2026, 2, 18, 9, 0, 0))
        self.assertEqual(row["effective_date"], datetime(2026, 2, 18, 9, 0, 0))
        self.assertEqual(row["observed_at"], observed_at)
        self.assertEqual(row["source_type"], "policy_document")

    def test_collect_recent_documents_aggregates_sources(self):
        collector = PolicyDocumentCollector()
        source = PolicyFeedSource(
            key="fed_policy",
            name="Fed policy",
            country="United States",
            country_ko="미국",
            category="Monetary Policy",
            category_ko="통화정책",
            feed_url="https://example.com/rss.xml",
        )
        collector.fetch_feed_xml = lambda _url: """
            <rss><channel><item>
              <title>Policy update</title>
              <link>https://example.com/policy</link>
              <description>desc</description>
              <pubDate>Tue, 18 Feb 2026 18:00:00 GMT</pubDate>
            </item></channel></rss>
        """  # type: ignore[method-assign]
        collector.save_to_db = lambda rows: len(list(rows))  # type: ignore[method-assign]

        result = collector.collect_recent_documents(hours=720, sources=[source])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["normalized_rows"], 1)
        self.assertEqual(result["db_affected"], 1)


if __name__ == "__main__":
    unittest.main()
