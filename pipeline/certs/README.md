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

## The one file here

`sectigo_public_server_auth_ca_dv_r36.pem`

- **Subject:** `C=GB, O=Sectigo Limited, CN=Sectigo Public Server Authentication CA DV R36`
- **Issuer:** `C=GB, O=Sectigo Limited, CN=Sectigo Public Server Authentication Root R46` — a public
  root present in the standard `ca-certificates` bundle, so `openssl verify` of this file alone
  returns `OK` against the untouched system store.
- **Expires:** 2036-03-21 — no near-term renewal cliff.
- **Needed by:** `pipeline/pull_collateral_census.py` (Union Auction, `--venue auct`).
- **Fetched from** the AIA URL named by the leaf itself:
  `http://crt.sectigo.com/SectigoPublicServerAuthenticationCADVR36.crt` (DER → PEM).

## What this cost before it was found

`data-collateral-census.yml` runs daily. From roughly 2026-08-10 the Union Auction pull returned
nothing, because `pull_collateral_census.py` passed `-s` to curl and **never checked curl's exit
code** — a TLS failure therefore surfaced only as `json.loads` complaining
`Expecting value: line 1 column 1 (char 0)`, which reads like a bad response body rather than a
connection that never completed. It was misread as a datacenter geoblock. The puller now reports
curl's exit status and stderr, so the next occurrence names itself.

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
