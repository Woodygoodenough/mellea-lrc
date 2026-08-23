# Settling every occurrence the arms disagree about

23 August 2026. Run over `false-citation-bench-v2` with the four model-free
arms. The rule is that wherever two arms differ about a span, one of them is
wrong or the gold is, and those are the only places worth a person's time.

## 1. What the disagreement actually is

43 occurrences of 583. They split cleanly, and only two needed adjudicating.

| who finds it | count | what it means |
|---|---:|---|
| production, layout-tolerant, layout-tolerant-wide | 37 | eyecite alone misses it |
| layout-tolerant, layout-tolerant-wide | 3 | needs the relaxed tokenizer |
| layout-tolerant-wide | 1 | needs the wide reporter-to-page join |
| **nobody** | **2** | **the gold has it and no arm reaches it** |

**The 41 are not disagreements about the document.** Every one is found by
`layout-tolerant-wide`, and each weaker arm misses exactly what its design
cannot reach. That is the arms working as intended, not a gold problem, and
nothing about them needs deciding.

## 2. The two nobody finds, settled against the page

Both are in the Chelsea Montes filings, both in a table of authorities, and
both were cropped out of the PDF and read.

**`796 F. Supp. 2d 1013` in document 021.** The page prints, in an ordinary
table-of-authorities row:

    Loos v. Lowe's
        796 F. Supp. 2d 1013, 1023 (D. Ariz. 2011)……………………19

**`2016 WL 9137645` in document 022.** The same, on its own row:

    Doe v. Rose,
        2016 WL 9137645, at 3 (C.D. Cal. July 25, 2016)……………6

**The gold is right in both cases and stays.** What the extractor is given is
not what the page says: the table reader emits the columns out of order, so
the exported text reads

    1013, 1023 (D. Ariz. 2011)   …   | )……………… |
    | 796 F. Supp. 2d

with the page number arriving before the volume and reporter. No tokenizer can
recover a citation from parts delivered in the wrong order — the fix is
structural, and it is the table-handling direction already recorded.

**So no gold changed and no extractor changed**, and the scores are unmoved:

| arm | true positives | false positives | recall |
|---|---:|---:|---:|
| eyecite | 542 | 0 | 92.6% |
| production | 579 | 0 | 99.0% |
| layout-tolerant | 582 | 0 | 99.5% |
| layout-tolerant-wide | 583 | 0 | 99.7% |

## 3. Two things the adjudication turned up on the way

**`page_crops` could not see a table at all.** It placed items by reading
`.text`, and a table has none — it becomes markdown. So a span inside a table
mapped to no region and produced no image, which is the one place this project
most needs to look, since a table of authorities is where these citations are.
Fixed by placing the whole table on its own box.

**The page explains an earlier flag.** The case-name check had reported
`958 F. Supp. 456` as *Loos v. Lowe's* where the archive says *Spratt v.
Northern Automotive Corp.* The page shows why, and the archive is right:

    Loos v. Lowe's
        796 F. Supp. 2d 1013, 1023 (D. Ariz. 2011)……………………19
    ...
    Spratt v. Northern Automotive Corp.
        958 F. Supp. 456, 462 (D. Ariz. 1996)…………………………19

Adjacent rows. The extractor attached the name from one row to the citation in
another. That is an extraction fault, not a defect in the filing, and it is the
shape to expect from every case-name flag that sits in a table of authorities.
