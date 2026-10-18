"""Whole-source preservation check only; no Java, Docker, network, or artifact reads."""
from pathlib import Path
import re
import unittest

import verify_decoder_stdout_fixture as protocol


class DecoderStdoutSource(unittest.TestCase):
    def test_entire_original_source_is_preserved_by_exact_stdout_transform(self):
        source = (Path(__file__).resolve().parent / protocol.JAVA_RELATIVE).read_bytes()
        original = protocol.original_source(source)
        self.assertEqual(protocol.sha(original), protocol.ORIGINAL_SHA)
        self.assertEqual(source.count(b'System.setOut('), 1)
        self.assertIn(protocol.MAIN_ROUTING.encode(), source)
        self.assertRegex('org/apache/iceberg/ClosedCopyDecoder$JsonHolder.class',
            r'^org/apache/iceberg/ClosedCopyDecoder(?:\$[A-Za-z0-9_]+)*\.class$')
        classes = re.findall(rb'\bclass ([A-Za-z0-9_]+)', source)
        self.assertLessEqual(len(classes), 64)


if __name__ == '__main__':
    unittest.main(verbosity=2)
