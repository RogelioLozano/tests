"""Animation endpoints.

The contract is asynchronous by design: `POST` answers 202 with a job, and
clients poll `GET`. The inline queue happens to finish the work before the
response is written, but nothing here promises that — which is exactly what
lets a background worker take over later with no client change.

Handlers stay thin: parse, delegate to the application service, map the result.
No orchestration, no I/O.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from fastapi.responses import RedirectResponse, StreamingResponse

from app.api.deps import AnimationServiceDep, RenderQuota
from app.api.schemas import (
    AnimationJobListResponse,
    AnimationJobResponse,
    CreateAnimationRequest,
    SceneSourceResponse,
)

router = APIRouter(prefix="/animations", tags=["animations"])

_STREAM_CHUNK = 64 * 1024


@router.post(
    "",
    response_model=AnimationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a prompt and start a render job",
    dependencies=[RenderQuota],
)
def create_animation(
    payload: CreateAnimationRequest, service: AnimationServiceDep
) -> AnimationJobResponse:
    job = service.submit_prompt(payload.prompt, payload.quality)
    return AnimationJobResponse.from_domain(job)


@router.get("", response_model=AnimationJobListResponse, summary="List render jobs")
def list_animations(
    service: AnimationServiceDep,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> AnimationJobListResponse:
    return AnimationJobListResponse.from_domain(
        service.list_jobs(limit=limit, offset=offset)
    )


@router.get(
    "/{job_id}", response_model=AnimationJobResponse, summary="Read one render job"
)
def get_animation(job_id: str, service: AnimationServiceDep) -> AnimationJobResponse:
    return AnimationJobResponse.from_domain(service.get_job(job_id))


@router.get(
    "/{job_id}/source",
    response_model=SceneSourceResponse,
    summary="Read the generated Manim source for a job",
)
def get_animation_source(
    job_id: str, service: AnimationServiceDep
) -> SceneSourceResponse:
    job = service.get_job(job_id)
    return SceneSourceResponse(
        job_id=job.id, scene_name=job.scene_name, code=job.generated_code
    )


@router.get("/{job_id}/video", summary="Download the rendered video")
def get_animation_video(job_id: str, service: AnimationServiceDep):
    download = service.open_artifact(job_id)
    if download.url is not None:
        # Cloud storage: hand the client a presigned URL instead of proxying.
        return RedirectResponse(download.url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    headers = {"Content-Disposition": f'inline; filename="{job_id}.mp4"'}
    if download.size_bytes is not None:
        headers["Content-Length"] = str(download.size_bytes)
    return StreamingResponse(
        _chunks(download.stream), media_type=download.content_type, headers=headers
    )


def _chunks(stream):
    with stream:
        while chunk := stream.read(_STREAM_CHUNK):
            yield chunk
