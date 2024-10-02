"""
API operations on the contents of a data library.
"""

import logging
import shutil
import tempfile
from typing import (
    List,
    Optional,
)

from fastapi import (
    Body,
    Depends,
    Request,
    UploadFile,
)
from starlette.datastructures import UploadFile as StarletteUploadFile

from galaxy.managers.context import (
    ProvidesHistoryContext,
    ProvidesUserContext,
)
from galaxy.schema.fields import DecodedDatabaseIdField
from galaxy.schema.library_contents import (
    AnyLibraryContentsCreatePayload,
    AnyLibraryContentsCreateResponse,
    AnyLibraryContentsShowResponse,
    AnyLibraryId,
    LibraryContentsDeletePayload,
    LibraryContentsDeleteResponse,
    LibraryContentsFileCreatePayload,
    LibraryContentsIndexListResponse,
)
from galaxy.webapps.galaxy.api import (
    depends,
    DependsOnTrans,
    Router,
)
from galaxy.webapps.galaxy.services.library_contents import (
    LibraryContentsService,
    MaybeLibraryFolderOrDatasetID,
)
from . import (
    APIContentTypeRoute,
    as_form,
)

log = logging.getLogger(__name__)

router = Router(tags=["libraries"])


class FormDataApiRoute(APIContentTypeRoute):
    match_content_type = "multipart/form-data"


class JsonApiRoute(APIContentTypeRoute):
    match_content_type = "application/json"


LibraryContentsCreateForm = as_form(LibraryContentsFileCreatePayload)


@router.cbv
class FastAPILibraryContents:
    service: LibraryContentsService = depends(LibraryContentsService)

    @router.get(
        "/api/libraries/{library_id}/contents",
        summary="Return a list of library files and folders.",
        deprecated=True,
    )
    def index(
        self,
        library_id: AnyLibraryId,
        trans: ProvidesUserContext = DependsOnTrans,
    ) -> LibraryContentsIndexListResponse:
        """This endpoint is deprecated. Please use GET /api/folders/{folder_id}/contents instead."""
        return self.service.index(trans, library_id)

    @router.get(
        "/api/libraries/{library_id}/contents/{id}",
        name="library_content",
        summary="Return a library file or folder.",
        deprecated=True,
    )
    def show(
        self,
        library_id: AnyLibraryId,
        id: MaybeLibraryFolderOrDatasetID,
        trans: ProvidesUserContext = DependsOnTrans,
    ) -> AnyLibraryContentsShowResponse:
        """This endpoint is deprecated. Please use GET /api/libraries/datasets/{library_id} instead."""
        return self.service.show(trans, id)

    @router.post(
        "/api/libraries/{library_id}/contents",
        summary="Create a new library file or folder.",
        deprecated=True,
        route_class_override=JsonApiRoute,
    )
    def create_json(
        self,
        library_id: AnyLibraryId,
        payload: AnyLibraryContentsCreatePayload,
        trans: ProvidesHistoryContext = DependsOnTrans,
    ) -> AnyLibraryContentsCreateResponse:
        """This endpoint is deprecated. Please use POST /api/folders/{folder_id} or POST /api/folders/{folder_id}/contents instead."""
        return self.service.create(trans, library_id, payload)

    @router.post(
        "/api/libraries/{library_id}/contents",
        summary="Create a new library file or folder.",
        deprecated=True,
        route_class_override=FormDataApiRoute,
    )
    async def create_form(
        self,
        request: Request,
        library_id: AnyLibraryId,
        payload: LibraryContentsFileCreatePayload = Depends(LibraryContentsCreateForm.as_form),
        files: Optional[List[UploadFile]] = None,
        trans: ProvidesHistoryContext = DependsOnTrans,
    ) -> AnyLibraryContentsCreateResponse:
        """This endpoint is deprecated. Please use POST /api/folders/{folder_id} or POST /api/folders/{folder_id}/contents instead."""
        # FastAPI's UploadFile is a very light wrapper around starlette's UploadFile
        if not files:
            data = await request.form()
            upload_files = []
            for upload_file in data.values():
                if isinstance(upload_file, StarletteUploadFile):
                    with tempfile.NamedTemporaryFile(
                        dir=trans.app.config.new_file_path, prefix="upload_file_data_", delete=False
                    ) as dest:
                        shutil.copyfileobj(upload_file.file, dest)  # type: ignore[misc]  # https://github.com/python/mypy/issues/15031
                    upload_file.file.close()
                    upload_files.append(dict(filename=upload_file.filename, local_filename=dest.name))
            payload.upload_files = upload_files

        return self.service.create(trans, library_id, payload)

    @router.put(
        "/api/libraries/{library_id}/contents/{id}",
        summary="Update a library file or folder.",
        deprecated=True,
    )
    def update(
        self,
        library_id: AnyLibraryId,
        id: DecodedDatabaseIdField,
        payload,
        trans: ProvidesUserContext = DependsOnTrans,
    ) -> None:
        """This endpoint is deprecated. Please use PATCH /api/libraries/datasets/{library_id} instead."""
        return self.service.update(trans, id, payload)

    @router.delete(
        "/api/libraries/{library_id}/contents/{id}",
        summary="Delete a library file or folder.",
        deprecated=True,
    )
    def delete(
        self,
        library_id: AnyLibraryId,
        id: DecodedDatabaseIdField,
        payload: Optional[LibraryContentsDeletePayload] = Body(None),
        trans: ProvidesHistoryContext = DependsOnTrans,
    ) -> LibraryContentsDeleteResponse:
        """This endpoint is deprecated. Please use DELETE /api/libraries/datasets/{library_id} instead."""
        return self.service.delete(trans, id, payload or LibraryContentsDeletePayload())
