"""
Try the anonymizer on text you type or paste — no corpus needed.

    python tools/try_anonymizer.py                       # built-in demo judgment
    python tools/try_anonymizer.py --header h.txt --body b.txt   # your own header / body text files
    python tools/try_anonymizer.py --keep-judges

The header should contain the party block (numbered names, then a role line such as "..... अर्जदार"),
advocate lines and "कोरम:" like a real judgment. The body is free text.
Prints the anonymized header/body, the entities that were found, and any leak the scanner reports.
"""
import os
import sys
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import anonymizer as A  # noqa: E402

DEMO_HEADER = """मुंबई उच्च न्यायालयातील
नागपूर खंडपीठात
2025 चा फौजदारी अर्ज (एपीएल) क्रमांक 1128

1. मिर्झा अस्लम बेग रशीद बेग,
वय: 29 वर्ष, व्यवसाय: मजूर,
रा. प्रभाग क्र.1, जामा मशिद जवळ,
तालुका मालेगाव, जिल्हा वाशिम.

2. शेख शफीक शेख बरकत,
वय: 45 वर्ष, व्यवसाय: मजूर,
..... अर्जदार
विरुद्ध

1. महाराष्ट्र राज्य,
मार्फत पोलिस स्टेशन ऑफिसर,
तेल्हारा पोलीस ठाणे,

2. राहुल पोपटराव तायडे (तक्रारदार)
वय: 42 वर्ष, व्यवसाय: पोलीस हवालदार,
.... गैर-अर्जदार
श्री. एस. व्ही. सिरपूरकर, अर्जदारांचे वकील.
श्रीमती स्नेहा धोटे, एपीपी गैर-अर्जदार क्रमांक 1 / राज्यांसाठी.
कोरम: उर्मिला जोशी-फाळके आणि
नंदेश एस. देशपांडे, जे. जे.
निकाल: (पर उर्मिला जोशी-फाळके, जे.)"""

DEMO_BODY = """1. श्री. रमेश पाटील यांनी साक्ष दिली. रमेश पाटलांनी सांगितले की मिर्झाने अर्ज केला.
2. अॅड. सुनील देशमुख यांनी युक्तिवाद केला की शेख शफीकने नकार दिला. सिरपूरकर यांनी हरकत घेतली.
3. संपर्क 9876543210, ईमेल ramesh@gmail.com, वाहन MH12AB1234, पिन 411001, दूरध्वनी 020-25671234.
4. मुदत 2023 2024 2025 पर्यंत. CNR MHAU019876543210. मुंबई उच्च न्यायालय आणि महाराष्ट्र राज्य यांनी तायडे यांना बोलावले."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--header")
    ap.add_argument("--body")
    ap.add_argument("--keep-judges", action="store_true")
    a = ap.parse_args()
    header = open(a.header, encoding="utf-8").read() if a.header else DEMO_HEADER
    body = open(a.body, encoding="utf-8").read() if a.body else DEMO_BODY
    doc = {"doc_id": "demo", "sections": {"header": header, "facts": body}, "metadata": {}, "cited_cases": []}
    out, rep = A.Anonymizer(A.Config(keep_judges=a.keep_judges)).anonymize_document(doc)
    print("── HEADER ──\n" + out["sections"]["header"])
    print("\n── BODY ──\n" + out["sections"]["facts"])
    print("\n── ENTITIES FOUND ──")
    for e in rep["entities"]:
        print(f"  {e['placeholder']:<16} <- {', '.join(e['names'])}   [{', '.join(e['sources'])}]")
    print("\ncounts:", rep["counts"])
    print("leaks :", rep["leaks"] or "none  (document would be marked fully anonymized)")
    print("\nTip: names that appear in the body but are NOT in the entities list were not recognised —")
    print("     that is exactly the kind of miss worth reporting.")


if __name__ == "__main__":
    main()
