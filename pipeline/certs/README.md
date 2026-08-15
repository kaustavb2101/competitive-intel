# `pipeline/certs/` — intermediate CA certificates that upstream servers forget to send

## Why this directory exists

A TLS server is supposed to send its **leaf certificate _and_ every intermediate** needed to chain up
to a trusted root. Browsers paper over a server that forgets: when the chain is incomplete they fetch
the missing intermediate themselves from the URL in the leaf's *Authority Information Access* (AIA)
extension. **OpenSSL and curl on Linux do not chase AIA.** So a site that "works in Chrome" and
"works from the laptop" can fail from every Linux CI runner with:

```
TLSv1.3 (OUT), TLS alert, unknown CA (560)
verify error:num=20:unable to get local issuer certificate
```

Storing the missing intermediate here and adding it to the trust bundle at request time repairs the
chain **without weakening verification**.

## This is not `curl -k`, and the difference matters

`-k` / `--insecure` disables verification altogether and would accept *any* certificate, including an
attacker's. What we do instead is supply a certificate the server should have sent. The signature
chain is still checked end to end: leaf → intermediate → **a root that was already in the system
store**. Nothing new is trusted that the system did not already trust.

The proof that it is a real check and not a bypass, measured 2026-08-15 against `service.auct.co.th:2368`:

| trust material passed to curl        | result                        |
| ------------------------------------ | ----------------------------- |
| system bundle alone                  | `HTTP 000` (chain fails)      |
| system bundle **+ this intermediate** | `HTTP 200`, 23,835,869 bytes |
| `-k` (for comparison only, not used) | `HTTP 200`                    |

If the fix were a bypass, the first row would have succeeded too.

## The files here

All three are loaded by `pipeline/lib/ca_bundle.py`, which any puller can use:
`curl_ca_args()` for curl-based pullers, `ssl_context()` for `urllib`-based ones. Each one verifies
`OK` against the untouched system store.

| file | serves | expires |
| --- | --- | --- |
| `sectigo_public_server_auth_ca_dv_r36.pem` | `service.auct.co.th` (Union Auction census) | 2036-03-21 |
| `sectigo_public_server_auth_ca_dv_e36.pem` | `muangthaicap.com` (rival promos) | 2036-03-21 |
| `globalsign_gcc_r6_alphassl_ca_2025.pem` | `www.sawad.co.th` (rival promos) | **2027-05-21** |

The GlobalSign one is the only near-term renewal to watch. When Sawad rotates its certificate, refetch
the intermediate from the leaf's AIA URL using the recipe below — the symptom will be the rival promo
feed going FROZEN again.

Each was fetched from the AIA URL named by the leaf itself:

- `http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt`
- `http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVE36.crt`
- `http://secure.globalsign.com/cacert/gsgccr6alphasslca2025.crt`

## What this cost before it was found

Three separate feeds, all recorded as geoblocks:

- **`data-collateral-census.yml`** (daily) returned nothing from roughly 2026-08-10, because
  `pull_collateral_census.py` passed `-s` to curl and **never checked curl's exit code**. A TLS
  failure therefore surfaced only as `json.loads` complaining `Expecting value: line 1 column 1
  (char 0)` — a message that reads like a bad response body rather than a connection that never
  completed. The puller now reports curl's exit status and names exit 60 as a chain failure.
- **The rival promo feed** sat FROZEN for 35 days — `check_feed_liveness.py` reported "4 identical
  readings 2026-07-19 .. 2026-08-13" for both Sawad and Tidlor — because Sawad and Muangthai were
  recorded in `data-thai-swarm.yml` as answering `000`, "no HTTP response at all". curl reports
  `000` for **any** transfer that did not complete, including one our own verification refused.

**The lesson worth keeping:** a geoblock *answers and refuses* (403, like `dataforthai.com`). A
broken chain never gets far enough to answer. Run `openssl s_client -connect host:443` before
recording any host as blocked — it distinguishes the two in one command.

## Adding another certificate here

1. Confirm the chain is genuinely incomplete, not that the site is down:
   `echo | openssl s_client -connect HOST:PORT -servername HOST` → look for
   `unable to get local issuer certificate`.
2. Read the AIA URL out of the leaf:
   `… | openssl x509 -noout -text | grep -A2 'Authority Information Access'`.
3. Download it and convert: `openssl x509 -inform DER -in x.crt -out x.pem`.
4. **Verify it chains to a root you already trust** — if this fails, do not commit it:
   `openssl verify -CAfile /etc/ssl/certs/ca-certificates.crt x.pem`  → must print `OK`.
5. Prove the system bundle alone still fails, so you know you fixed the chain rather than
   disabled the check.

Never commit a self-signed certificate or a private root here. If step 4 does not print `OK`, the
right response is to contact the site operator, not to widen our trust store.
