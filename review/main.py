# -*- coding: utf-8 -*-
"""paperbank-review — internal review panel (separate Cloud Run service; shares ONLY the Cloud SQL
DB + GCS bucket with the student bot). Whitelisted-phone + WhatsApp-OTP auth; queue of
awaiting_review contributions; approve -> promote into the live corpus; deny -> close. Either way
the contributor is notified. Minimal server-rendered HTML, no public bucket (images proxied)."""
import html
import logging
import re
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, Response, PlainTextResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from google.cloud import storage

from app.config import settings
from app.db import SessionLocal
from app import whatsapp
from review import auth, promote as promo

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.Client(timeout=httpx.Timeout(connect=5, read=30, write=30, pool=5))
    app.state.gcs = storage.Client(project=settings.gcp_project)
    yield
    app.state.http.close()


app = FastAPI(lifespan=lifespan, title="paperbank-review")


def get_session():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _norm_phone(p: str) -> str:
    return auth.normalize_phone(p)


def _me(request: Request) -> str | None:
    return auth.read_session(request.cookies.get(auth.COOKIE))


def _esc(x) -> str:
    return html.escape(str(x)) if x is not None else ""


# --------------------------------------------------------------------- HTML shell
_CSS = """body{font-family:system-ui,Arial,sans-serif;max-width:920px;margin:24px auto;padding:0 14px;color:#1a1a1a}
a{color:#1558d6;text-decoration:none}a:hover{text-decoration:underline}
.card{border:1px solid #ddd;border-radius:10px;padding:14px 16px;margin:12px 0}
.row{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.badge{background:#fde68a;color:#92400e;border-radius:6px;padding:2px 8px;font-size:12px;font-weight:600}
.muted{color:#666;font-size:13px}input,select,textarea{font:inherit;padding:8px;border:1px solid #ccc;border-radius:6px}
label{display:block;margin:8px 0 3px;font-size:13px;color:#444}
button{font:inherit;padding:9px 16px;border:0;border-radius:7px;cursor:pointer}
.go{background:#16a34a;color:#fff}.no{background:#dc2626;color:#fff}.pri{background:#1558d6;color:#fff}
img.pg{max-width:280px;border:1px solid #ccc;border-radius:6px;margin:6px;cursor:zoom-in}
.grid{display:flex;flex-wrap:wrap}fieldset{border:1px solid #ddd;border-radius:8px;margin:10px 0}
#lb{display:none;position:fixed;inset:0;background:rgba(0,0,0,.92);z-index:90;cursor:zoom-out;overflow:auto;text-align:center}
#lb img{max-width:98%;margin:1.5vh auto;box-shadow:0 0 24px #000}
#lb .hint{position:fixed;top:8px;left:0;right:0;color:#bbb;font-size:13px}"""


def _page(title: str, body: str, me: str | None = None) -> HTMLResponse:
    top = (f'<div class="row"><h2>PAU Muslim Ummah — Review</h2><div class="muted">{_esc(me)} · '
           f'<a href="/logout">log out</a></div></div>') if me else "<h2>PAU Muslim Ummah — Review</h2>"
    # Click-to-zoom lightbox: any <img class=pg> opens full-resolution (same auth'd /img proxy src);
    # click anywhere or press Esc to close. Vanilla JS/CSS, no library, no backend change.
    lightbox = ("<div id=lb onclick=\"this.style.display='none'\">"
                "<div class=hint>click anywhere or press Esc to close</div><img></div>"
                "<script>document.addEventListener('click',function(e){"
                "if(e.target.classList&&e.target.classList.contains('pg')){"
                "var l=document.getElementById('lb');l.querySelector('img').src=e.target.src;"
                "l.style.display='block';window.scrollTo(0,0);}});"
                "document.addEventListener('keydown',function(e){"
                "if(e.key==='Escape')document.getElementById('lb').style.display='none';});</script>")
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>{_esc(title)}</title>"
                        f"<meta name=viewport content='width=device-width,initial-scale=1'>"
                        f"<style>{_CSS}</style>{top}{body}{lightbox}")


# --------------------------------------------------------------------- health
@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


# --------------------------------------------------------------------- auth
@app.get("/login", response_class=HTMLResponse)
def login_form(err: str = ""):
    e = f"<p class='muted' style='color:#b91c1c'>{_esc(err)}</p>" if err else ""
    return _page("Login", f"""{e}<div class="card"><form method=post action="/login">
      <label>Your phone number (the one on the reviewer list)</label>
      <input name=phone placeholder="2348012345678" autofocus required>
      <p><button class=pri>Send me a code</button></p>
      <p class="muted">A 6-digit code will be sent to your WhatsApp.</p></form></div>""")


@app.post("/login")
def login_send(request: Request, phone: str = Form(...), s: Session = Depends(get_session)):
    p = _norm_phone(phone)
    # Generic outcome regardless of whether the number is a reviewer (don't reveal membership).
    rv = auth.active_reviewer(s, p)
    if rv and auth.can_request(s, p):
        code = auth.issue_otp(s, p)
        try:
            whatsapp.send_text(request.app.state.http, p,
                               f"Your PAU Muslim Ummah review code is {code}. It expires in 5 minutes.")
        except Exception:
            log.exception("otp_send_failed")
    return RedirectResponse(f"/verify?phone={p}", status_code=303)


@app.get("/verify", response_class=HTMLResponse)
def verify_form(phone: str = "", err: str = ""):
    e = f"<p class='muted' style='color:#b91c1c'>{_esc(err)}</p>" if err else ""
    return _page("Verify", f"""{e}<div class="card"><form method=post action="/verify">
      <input type=hidden name=phone value="{_esc(phone)}">
      <label>Enter the 6-digit code sent to your WhatsApp</label>
      <input name=code inputmode=numeric pattern="[0-9]*" maxlength=6 autofocus required>
      <p><button class=pri>Verify</button></p>
      <p class="muted">If you're on the reviewer list, a code was just sent. <a href="/login">Resend</a></p>
      <p class="muted">Didn't receive a code? Make sure your number is in international format
      (234&hellip;, not 0&hellip;).</p>
      </form></div>""")


@app.post("/verify")
def verify_check(phone: str = Form(...), code: str = Form(...), s: Session = Depends(get_session)):
    p = _norm_phone(phone)
    if auth.active_reviewer(s, p) and auth.verify_otp(s, p, code.strip()):
        resp = RedirectResponse("/", status_code=303)
        resp.set_cookie(auth.COOKIE, auth.issue_session(p), httponly=True, secure=True, samesite="lax",
                        max_age=settings.review_session_hours * 3600)
        return resp
    return RedirectResponse(f"/verify?phone={p}&err=Invalid+or+expired+code", status_code=303)


@app.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.COOKIE)
    return resp


# --------------------------------------------------------------------- queue
@app.get("/", response_class=HTMLResponse)
def queue(request: Request, s: Session = Depends(get_session)):
    me = _me(request)
    if not me:
        return RedirectResponse("/login", status_code=303)
    rows = s.execute(text(
        "SELECT c.id, c.contributor_school, c.course_code, c.course_title, c.year, c.exam_session, "
        "c.doc_type, c.likely_dup_of, c.created_at, "
        "(SELECT count(*) FROM contribution_pages cp WHERE cp.contribution_id=c.id) AS pages "
        "FROM contributions c WHERE c.status='awaiting_review' ORDER BY c.created_at ASC"
    )).mappings().all()
    if not rows:
        return _page("Queue", "<div class='card'>🎉 Queue is clear — no contributions awaiting review.</div>", me)
    items = []
    for r in rows:
        dup = " <span class=badge>LIKELY DUPLICATE</span>" if r["likely_dup_of"] else ""
        filing = " · ".join(x for x in [r["course_code"] or r["course_title"] or "(unread)", r["year"],
                                        r["exam_session"]] if x)
        items.append(f"""<div class="card"><div class="row">
          <div><a href="/c/{r['id']}"><b>{_esc(filing)}</b></a>{dup}<div class="muted">
          {_esc(r['contributor_school'] or '?')} · {r['pages']} page(s) · {r['created_at']:%Y-%m-%d %H:%M}</div></div>
          <a href="/c/{r['id']}">review →</a></div></div>""")
    return _page("Queue", f"<p class='muted'>{len(rows)} awaiting review (oldest first)</p>" + "".join(items), me)


# --------------------------------------------------------------------- detail
@app.get("/c/{cid}", response_class=HTMLResponse)
def detail(cid: int, request: Request, s: Session = Depends(get_session)):
    me = _me(request)
    if not me:
        return RedirectResponse("/login", status_code=303)
    c = s.execute(text("SELECT * FROM contributions WHERE id=:c"), {"c": cid}).mappings().first()
    if not c or c["status"] != "awaiting_review":
        return _page("Not found", "<div class='card'>This contribution isn't awaiting review (already handled?). "
                                   "<a href='/'>back to queue</a></div>", me)
    pages = s.execute(text("SELECT id, page_order FROM contribution_pages WHERE contribution_id=:c ORDER BY page_order"),
                      {"c": cid}).mappings().all()
    imgs = "".join(f'<img class=pg src="/img/contrib/{p["id"]}" title="page {p["page_order"]}">' for p in pages)

    sess = c["exam_session"] or ""
    opts = "".join(f'<option value="{v}"{" selected" if sess == v else ""}>{v}</option>'
                   for v in ("", "exam", "CA1", "CA2"))
    dt = c["doc_type"] or ""
    dopts = "".join(f'<option value="{v}"{" selected" if dt == v else ""}>{v or "(unknown)"}</option>'
                    for v in ("", "exam", "CA"))

    dup_block = ""
    dedup_field = ""
    if c["likely_dup_of"]:
        dpages = s.execute(text("SELECT id FROM pending_papers WHERE id=:i OR id IN "
                                "(SELECT page_row_id FROM exam_group WHERE logical_exam_id=(SELECT logical_exam_id "
                                "FROM exam_group WHERE page_row_id=:i)) ORDER BY id"), {"i": c["likely_dup_of"]}).scalars().all()
        dimgs = "".join(f'<img class=pg src="/img/paper/{pid}">' for pid in dpages)
        dup_block = (f'<fieldset><legend>⚠ Likely duplicate of existing paper #{c["likely_dup_of"]}</legend>'
                     f'<div class="grid">{dimgs}</div></fieldset>')
        dedup_field = """<fieldset><legend>This duplicates an existing paper — choose</legend>
          <label><input type=radio name=dedup_choice value="keep_both" checked> Keep both (add alongside)</label>
          <label><input type=radio name=dedup_choice value="replace"> Replace (retire the old one — reversible)</label>
          </fieldset>"""

    bv = _esc(c["bot_validation"])[:600]
    body = f"""<p><a href="/">← queue</a></p>
    <div class="card"><b>Contribution #{cid}</b> · {_esc(c['contributor_school'] or '?')} ·
      {len(pages)} page(s) · submitted {c['created_at']:%Y-%m-%d %H:%M}</div>
    <div class="card"><div class="grid">{imgs}</div></div>
    {dup_block}
    <div class="card"><b>Bot validation:</b> <span class="muted">{bv}</span></div>
    <div class="card"><form method=post action="/c/{cid}/approve">
      <b>Filing (correct it if the bot's read is off — you're the final authority):</b>
      <label>Course code</label><input name=course_code value="{_esc(c['course_code'])}">
      <label>Course title</label><input name=course_title value="{_esc(c['course_title'])}">
      <label>Year</label><input name=year value="{_esc(c['year'])}" placeholder="2024">
      <label>Session</label><select name=exam_session>{opts}</select>
      <label>Type</label><select name=doc_type>{dopts}</select>
      {dedup_field}
      <p><button class=go>Approve &amp; publish</button></p></form></div>
    <div class="card"><form method=post action="/c/{cid}/deny">
      <label>Deny with an optional reason (sent to the contributor):</label>
      <textarea name=comment rows=2 style="width:100%" placeholder="e.g. pages were too blurry to read"></textarea>
      <p><button class=no>Deny</button></p></form></div>"""
    return _page(f"Contribution {cid}", body, me)


# --------------------------------------------------------------------- approve / deny
@app.post("/c/{cid}/approve")
def approve(cid: int, request: Request, course_code: str = Form(""), course_title: str = Form(""),
            year: str = Form(""), exam_session: str = Form(""), doc_type: str = Form(""),
            dedup_choice: str = Form("keep_both"), s: Session = Depends(get_session)):
    me = _me(request)
    if not me:
        return RedirectResponse("/login", status_code=303)
    filing = {"course_code": (course_code.strip().upper().replace(" ", "") or None),
              "course_title": (course_title.strip() or None), "year": (re.sub(r"\D", "", year)[:9] or None),
              "exam_session": (exam_session or None), "doc_type": (doc_type or None)}
    n = promo.promote(s, request.app.state.gcs, request.app.state.http, cid, filing, dedup_choice, me)
    log.info("approved", extra={"cid": cid, "by": me, "pages": n})
    return RedirectResponse("/", status_code=303)


@app.post("/c/{cid}/deny")
def deny(cid: int, request: Request, comment: str = Form(""), s: Session = Depends(get_session)):
    me = _me(request)
    if not me:
        return RedirectResponse("/login", status_code=303)
    promo.deny(s, request.app.state.http, cid, comment.strip() or None, me)
    log.info("denied", extra={"cid": cid, "by": me})
    return RedirectResponse("/", status_code=303)


# --------------------------------------------------------------------- image proxy (auth'd; bucket private)
def _serve_object(request: Request, gcs_object: str | None):
    if not gcs_object:
        return Response(status_code=404)
    raw = request.app.state.gcs.bucket(settings.gcs_bucket).blob(gcs_object).download_as_bytes()
    ext = gcs_object.rsplit(".", 1)[-1].lower() if "." in gcs_object else "jpg"
    mt = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "heic": "image/heic"}.get(ext, "image/jpeg")
    return Response(content=raw, media_type=mt)


@app.get("/img/contrib/{page_id}")
def img_contrib(page_id: int, request: Request, s: Session = Depends(get_session)):
    if not _me(request):
        return Response(status_code=401)
    obj = s.execute(text("SELECT gcs_object FROM contribution_pages WHERE id=:i"), {"i": page_id}).scalar()
    return _serve_object(request, obj)


@app.get("/img/paper/{pid}")
def img_paper(pid: int, request: Request, s: Session = Depends(get_session)):
    if not _me(request):
        return Response(status_code=401)
    obj = s.execute(text("SELECT gcs_object FROM pending_papers WHERE id=:i"), {"i": pid}).scalar()
    return _serve_object(request, obj)
