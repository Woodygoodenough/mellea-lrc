# CourtListener access proxy

A forward-and-cache layer between this project and CourtListener, deployed on
Modal as `courtlistener-access`. It forwards a request unchanged, caches the
response, and returns it — no renamed fields, no wrapped bodies, no composing
several upstream calls into one. A proxy that reshapes responses moves bugs out
of the pipeline and into a place nobody is testing.

It exists because of one number.

## 125 requests per token per day

That is CourtListener's free-tier allowance, and it is the binding constraint on
every evaluation this project runs. One sweep of the LePhantomCite eval split
needs 1,197 distinct locator lookups. At one token that is ten days; at three,
a little over three.

Two consequences follow, and both are this service's whole purpose:

- **The cache is the corpus.** Once a response is stored it costs nothing
  forever, so the cached bucket — not the API — is what makes an evaluation
  repeatable. Losing it means weeks, not minutes.
- **Rotation is not an optimization.** Three tokens is three times the daily
  budget. `COURTLISTENER_API_TOKEN_1`, `_2`, `_3`, … are collected in order and
  used round-robin.

## The two rules that keep the cache correct

**The key never changes.** It is

```
sha256("METHOD|endpoint|urlencode(sorted(params))|urlencode(sorted(data))")
```

stored at `{R2_PREFIX}/{key}.json`. `endpoint` is the path below the API root
with no leading slash and its trailing slash kept — `search/`,
`citation-lookup/`, `dockets/42/`. Thousands of responses are already stored
under this scheme, and at 125 lookups a day an orphaned cache costs weeks to
rebuild, so [`cache.py`](cache.py) is pinned by a test against twelve real
objects recorded from the live bucket. If that test fails, the change is wrong,
not the test.

**Only a success is stored.** A cached failure answers every later request for
that citation with the same failure and never retries. A cached `429` freezes a
rate limit into the record; a cached `401` freezes a credential problem into it.
Neither has anything to do with the citation. `should_store` is the single place
that decides, and it says yes only to a 2xx carrying a body.

Five objects violating that rule were found in the live bucket — two 429s, a
401, a 404 and a 400, each stored as a bare status code with a null response —
and removed.

## Two envelope formats, both readable

The bucket contains records in two shapes, and the older one is not garbage:

| version | shape | count when last scanned |
|---|---|---:|
| 2 (written now) | `{key, method, endpoint, params, data, url, status_code, response, cached_at}` | 3,212 |
| 1 (older) | `{status_code, content: <base64 body>, content_type}` | 718 |

Every version-1 object holds a real 200 response whose content decodes to valid
JSON. `read_envelope` reads both. Treating the older shape as unreadable would
discard 718 answers and spend roughly six days of quota re-fetching what is
already stored.

## Secrets

```env
# Modal secret: courtlistener
COURTLISTENER_API_TOKEN_1=<token>
COURTLISTENER_API_TOKEN_2=<token>     # optional; each one is another 125/day
COURTLISTENER_API_TOKEN_3=<token>
COURTLISTENER_BASE_URL=https://www.courtlistener.com/api/rest/v4/

# Modal secret: courtlistener-r2-cache
R2_BUCKET=cl-cache
R2_PREFIX=courtlistener/v4
R2_ACCOUNT_ID=<cloudflare-account-id>
R2_ACCESS_KEY_ID=<r2-access-key>
R2_SECRET_ACCESS_KEY=<r2-secret-key>
R2_REGION=auto
```

`modal secret create --force` **replaces** a secret rather than merging into it,
so always supply every key. Dropping `R2_BUCKET` by supplying only the rotated
credentials silently points the cache at nothing.

## Deploy

```bash
uv run --group modal modal deploy scripts/modal/courtlistener/server.py
```

Then check it, and confirm it sees every token:

```bash
curl -s "$COURTLISTENER_BASE_URL/health"
# {"status":"ok","app":"courtlistener-access","tokens":3,"bucket":"cl-cache"}
```

A response carries `x-cache: hit` or `x-cache: miss`, which is the cheapest way
to tell a cache problem from a quota problem. When every token is spent the
service answers `429` with `retry-after` set from the reset CourtListener names,
so a caller can stop rather than retry into a wall.

## Repairing the cache

```bash
python -m scripts.modal.courtlistener.repair_cache            # report only
python -m scripts.modal.courtlistener.repair_cache --delete   # remove them
```

It decides with `read_envelope`, the same function the service reads with, so it
cannot disagree with the service about what is servable. Nothing is removed
without `--delete`, and what is removed is written to a backup file first —
looking unfamiliar is not the same as being unusable, and the 718 older-envelope
objects are the reason that distinction matters.
