"""Autoload extraction regression tests; run with Python + ndspy, no build."""
import struct
import unittest

from prepare_nsmb import extract_arm9_runtime


class AutoloadExtractionTest(unittest.TestCase):
    def setUp(self):
        self.base = 0x02000000
        self.image = bytearray(256)
        # Module parameters at +0x20, signature at +0x3c.
        struct.pack_into('<III', self.image, 32, self.base + 128,
                         self.base + 164, self.base + 192)
        struct.pack_into('<II', self.image, 60, 0xDEC00621, 0x2106C0DE)
        struct.pack_into('<III', self.image, 128, 0x01FF8000, 8, 0)
        struct.pack_into('<III', self.image, 140, 0x027E0000, 4, 0)
        struct.pack_into('<III', self.image, 152, 0x02043380, 12, 0)
        self.image[192:216] = bytes(range(24))

    def test_exact_copy_after_itcm_and_dtcm(self):
        destination, data = extract_arm9_runtime(bytes(self.image), self.base)
        self.assertEqual(destination, 0x02043380)
        self.assertEqual(data, bytes(range(12, 24)))

    def test_bss_only_record_is_not_code(self):
        struct.pack_into('<I', self.image, 36, self.base + 176)
        struct.pack_into('<III', self.image, 164, 0x02085880, 0, 0x12E60)
        self.assertEqual(extract_arm9_runtime(bytes(self.image), self.base)[1], bytes(range(12, 24)))

    def test_rejects_bad_table(self):
        for end in (self.base + 165, self.base + 300, self.base + 100):
            with self.subTest(end=end):
                struct.pack_into('<I', self.image, 36, end)
                with self.assertRaises(ValueError):
                    extract_arm9_runtime(bytes(self.image), self.base)

    def test_rejects_source_outside_image(self):
        struct.pack_into('<I', self.image, 40, self.base + 250)
        with self.assertRaises(ValueError):
            extract_arm9_runtime(bytes(self.image), self.base)

    def test_rejects_copy_outside_ram(self):
        struct.pack_into('<I', self.image, 152, 0x023FFFFC)
        with self.assertRaises(ValueError):
            extract_arm9_runtime(bytes(self.image), self.base)

    def test_rejects_missing_or_duplicate_signature(self):
        for duplicate in (False, True):
            with self.subTest(duplicate=duplicate):
                image = self.image.copy()
                if duplicate:
                    image[80:88] = image[60:68]
                else:
                    image[60:68] = bytes(8)
                with self.assertRaises(ValueError):
                    extract_arm9_runtime(bytes(image), self.base)

    def test_rejects_ambiguous_main_ram_copies(self):
        struct.pack_into('<I', self.image, 128, 0x02001000)
        with self.assertRaises(ValueError):
            extract_arm9_runtime(bytes(self.image), self.base)


if __name__ == '__main__':
    unittest.main()
