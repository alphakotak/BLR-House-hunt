"""Compose and send the shortlist as an HTML email digest."""
from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from html import escape
from typing import List

from ..config import EmailSettings
from ..matcher import MatchResult


def _snippet(text: str, limit: int = 320) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_html(results: List[MatchResult]) -> str:
    cards = []
    for r in results:
        p = r.post
        reasons = "".join(f"<li>{escape(x)}</li>" for x in r.reasons)
        posted = p.posted_at.strftime("%d %b, %H:%M") if p.posted_at else "unknown time"
        rent = f"₹{r.rent:,}/mo" if r.rent else "rent not stated"
        cards.append(
            f"""
            <div style="border:1px solid #e5e7eb;border-radius:12px;padding:16px;margin:0 0 14px;">
              <div style="font-size:13px;color:#6b7280;">
                {escape(p.group_name or p.source)} · {escape(posted)} · score {r.score}
              </div>
              <div style="font-size:16px;font-weight:600;margin:6px 0;">{escape(rent)}</div>
              <div style="font-size:14px;color:#111827;line-height:1.45;">
                {escape(_snippet(p.text))}
              </div>
              <ul style="font-size:12px;color:#374151;margin:10px 0 12px;padding-left:18px;">{reasons}</ul>
              <a href="{escape(p.url)}"
                 style="display:inline-block;background:#111827;color:#fff;text-decoration:none;
                        padding:8px 14px;border-radius:8px;font-size:13px;">Open post</a>
            </div>
            """
        )
    body = "".join(cards) if cards else "<p>No new matches this run.</p>"
    return f"""\
<!doctype html><html><body style="margin:0;background:#f9fafb;padding:24px;
    font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:640px;margin:0 auto;">
    <h2 style="margin:0 0 4px;">Bellandur flat shortlist</h2>
    <p style="color:#6b7280;margin:0 0 20px;font-size:14px;">
      {len(results)} new match(es) near RMZ Ecoworld.
    </p>
    {body}
    <p style="color:#9ca3af;font-size:12px;margin-top:24px;">
      Auto-generated. Tune matches in config/criteria.yaml.
    </p>
  </div>
</body></html>"""


def build_text(results: List[MatchResult]) -> str:
    if not results:
        return "No new matches this run."
    lines = [f"{len(results)} new match(es) near RMZ Ecoworld.\n"]
    for i, r in enumerate(results, 1):
        rent = f"Rs {r.rent:,}/mo" if r.rent else "rent n/a"
        lines.append(f"{i}. [{r.score}] {rent} - {r.post.group_name}")
        lines.append(f"   {_snippet(r.post.text, 200)}")
        lines.append(f"   {r.post.url}\n")
    return "\n".join(lines)


def send_digest(settings: EmailSettings, results: List[MatchResult]) -> None:
    settings.validate()
    msg = EmailMessage()
    subject_count = len(results)
    msg["Subject"] = f"[Flat-hunt] {subject_count} new Bellandur match(es)"
    msg["From"] = settings.sender
    msg["To"] = ", ".join(settings.recipients)
    msg.set_content(build_text(results))
    msg.add_alternative(build_html(results), subtype="html")

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.host, settings.port, timeout=30) as server:
        server.starttls(context=context)
        server.login(settings.user, settings.password)
        server.send_message(msg)
