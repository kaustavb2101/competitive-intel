"""Trust material for upstream servers that send an incomplete certificate chain.

THE PROBLEM THIS SOLVES
-----------------------
A TLS server must send its leaf certificate AND every intermediate needed to reach a trusted root.
Several sites this project pulls from send only the leaf. Browsers paper over that by fetching the
missing intermediate from the leaf's Authority Information Access (AIA) extension; OpenSSL and curl
on Linux do not chase AIA. The result is a site that works in Chrome, works from the owner's Windows
laptop, and fails from every Linux runner with:

    TLSv1.3 (OUT), TLS alert, unknown CA (560)
    verify error:num=20:unable to get local issuer certificate

That asymmetry is a diagnosis trap. It looks exactly like a datacenter geoblock, and it was recorded
as one for three different hosts in this repo before anyone ran `openssl s_client` (2026-08-15):

  * service.auct.co.th   — "newly-applied geoblock against the Azure runner IP range"
  * www.sawad.co.th      — "blocked from a foreign IP"
  * muangthaicap.com     — "blocked from a foreign IP"

All three were incomplete chains. None were geoblocked. Union Auction had silently stopped feeding
the daily collateral price census; Sawad and MTC left the rival promo feed FROZEN for 35 days
(check_feed_liveness.py: "4 identical readings 2026-07-19 .. 2026-08-13").

THIS IS A CHAIN REPAIR, NOT `curl -k`
-------------------------------------
`-k` / `verify=False` accepts ANY certificate, including an attacker's. Here we supply a certificate
the server should have sent and leave verification fully on: the signature chain is still checked
leaf -> intermediate -> a root that was ALREADY in the system store. Nothing is trusted that was not
trusted before. Every PEM in pipeline/certs/ has been checked with

    openssl verify -CAfile /etc/ssl/certs/ca-certificates.crt <pem>   # must print OK

so each one provably descends from a public root. See pipeline/certs/README.md for the measurements
and for how to add another.

USAGE
-----
    from lib.ca_bundle import curl_ca_args, ssl_context

    subprocess.run(["curl", "-s", url] + curl_ca_args())        # curl-based pullers
    urllib.request.urlopen(req, context=ssl_context())          # urllib-based pullers

Both degrade to "system roots only" when pipeline/certs/ is empty or unreadable, so a missing file
produces an honest TLS error rather than an import crash.
"""
import atexit
import glob
import os
import ssl
import tempfile

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CERT_DIR = os.path.join(_HERE, "certs")

_curl_args_cache = []
_ctx_cache = []


def extra_pems():
    """Every committed intermediate, sorted so the generated bundle is deterministic."""
    try:
        return sorted(glob.glob(os.path.join(CERT_DIR, "*.pem")))
    except OSError:
        return []


def _extra_pem_text():
    out = []
    for p in extra_pems():
        try:
            with open(p, "r", encoding="utf-8") as fh:
                out.append(fh.read())
        except OSError:
            continue
    return "\n".join(out)


def curl_ca_args():
    """['--cacert', <bundle>] trusting the system roots PLUS every committed intermediate.

    curl's --cacert REPLACES the trust store rather than adding to it, so the bundle is written as
    system-roots-first and the real public root stays the anchor. Returns [] when there is nothing to
    add, leaving curl on its normal defaults.
    """
    if _curl_args_cache:
        return _curl_args_cache[0]

    extra = _extra_pem_text()
    if not extra.strip():
        _curl_args_cache.append([])
        return []

    system = ssl.get_default_verify_paths().cafile
    if not system or not os.path.exists(system):
        try:
            import certifi
            system = certifi.where()
        except Exception:
            system = None

    fd, path = tempfile.mkstemp(prefix="ca_bundle_", suffix=".pem")
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        if system:
            with open(system, "r", encoding="utf-8", errors="replace") as fh:
                out.write(fh.read())
            out.write("\n")
        out.write(extra)
    atexit.register(lambda: os.path.exists(path) and os.unlink(path))

    _curl_args_cache.append(["--cacert", path])
    return _curl_args_cache[0]


def ssl_context():
    """An SSLContext with the system defaults PLUS every committed intermediate.

    create_default_context() keeps hostname checking and CERT_REQUIRED on; load_verify_locations only
    ADDS chain-building material, so this cannot loosen verification.
    """
    if _ctx_cache:
        return _ctx_cache[0]

    ctx = ssl.create_default_context()
    extra = _extra_pem_text()
    if extra.strip():
        try:
            ctx.load_verify_locations(cadata=extra)
        except Exception as exc:                       # noqa: BLE001 - a bad PEM must not kill the pull
            print("ca_bundle: could not load pipeline/certs (%s); using system roots only." % exc)
    _ctx_cache.append(ctx)
    return ctx
