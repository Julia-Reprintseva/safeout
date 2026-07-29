import mimetypes
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session_factory
from core.models import DateSession, SessionFile, FileType, Escalation, EscalationStatus
from core.config import settings

app = FastAPI(docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="templates")

MAPS_KEY = ""  # set via env if using Google Maps


@app.get("/alert/{token}", response_class=HTMLResponse)
async def alert_page(request: Request, token: str):
    async with async_session_factory() as db:
        result = await db.execute(
            select(DateSession).where(DateSession.alert_token == token)
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(404)

        from core.models import User
        user = await db.get(User, session.user_id)

        files_result = await db.execute(
            select(SessionFile).where(SessionFile.session_id == session.id)
        )
        files = files_result.scalars().all()

        file_data = []
        for f in files:
            file_data.append({
                "url": f"{settings.app_base_url}/alert/{token}/files/{f.id}",
                "name": f.original_name or f"file-{f.id}",
                "is_image": f.file_type == FileType.PHOTO,
            })

        lang = user.language.value if user else "ru"
        is_sos = session.status.value == "sos"

        ack_result = await db.execute(
            select(Escalation)
            .where(Escalation.session_id == session.id)
            .where(Escalation.status == EscalationStatus.ACKNOWLEDGED)
        )
        acknowledged = ack_result.scalars().first() is not None

        return templates.TemplateResponse("alert.html", {
            "request": request,
            "lang": lang,
            "user_name": user.first_name if user else "",
            "is_sos": is_sos,
            "lat": session.last_lat,
            "lon": session.last_lon,
            "date_name": session.date_name,
            "date_profile_url": session.date_profile_url,
            "meeting_place": session.meeting_place,
            "destination": session.destination,
            "hotel_info": session.hotel_info,
            "car_plate": session.car_plate,
            "extra_info": session.extra_info,
            "expected_return": session.expected_return.strftime("%H:%M %d.%m") if session.expected_return else None,
            "files": file_data,
            "acknowledged": acknowledged,
            "ack_url": f"{settings.app_base_url}/alert/{token}/ack",
            "maps_key": MAPS_KEY,
        })


@app.get("/alert/{token}/files/{file_id}")
async def alert_file(token: str, file_id: int):
    """Streams an uploaded file to trusted contacts by proxying it through the
    Bot API — files are stored as Telegram file_ids, not on our own storage
    (no S3/R2 configured by default). Gated by the same alert_token as the
    page itself."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(DateSession).where(DateSession.alert_token == token)
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(404)

        file_row = await db.get(SessionFile, file_id)
        if not file_row or file_row.session_id != session.id:
            raise HTTPException(404)
        tg_file_id = file_row.s3_key

    async with httpx.AsyncClient() as client:
        meta = await client.get(
            f"https://api.telegram.org/bot{settings.bot_token}/getFile",
            params={"file_id": tg_file_id},
        )
        if meta.status_code != 200:
            raise HTTPException(404)
        file_path = meta.json()["result"]["file_path"]

        file_resp = await client.get(
            f"https://api.telegram.org/file/bot{settings.bot_token}/{file_path}"
        )
        if file_resp.status_code != 200:
            raise HTTPException(404)

    media_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    return Response(content=file_resp.content, media_type=media_type)


@app.post("/alert/{token}/ack")
async def acknowledge_alert(token: str):
    async with async_session_factory() as db:
        result = await db.execute(
            select(DateSession).where(DateSession.alert_token == token)
        )
        session = result.scalars().first()
        if not session:
            raise HTTPException(404)

        esc_result = await db.execute(
            select(Escalation)
            .where(Escalation.session_id == session.id)
            .where(Escalation.status == EscalationStatus.SENT)
        )
        escalations = esc_result.scalars().all()
        for e in escalations:
            e.status = EscalationStatus.ACKNOWLEDGED
            e.acknowledged_at = datetime.now(timezone.utc)

        await db.commit()
    return {"ok": True}
