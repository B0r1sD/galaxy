from enum import Enum
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union,
)

from pydantic import (
    Field,
    RootModel,
)

from galaxy.schema.fields import (
    DecodedDatabaseIdField,
    EncodedDatabaseIdField,
    EncodedLibraryFolderDatabaseIdField,
    LibraryFolderDatabaseIdField,
)
from galaxy.schema.schema import (
    Model,
    TagCollection,
)


class UploadOption(str, Enum):
    upload_file = "upload_file"
    upload_paths = "upload_paths"
    upload_directory = "upload_directory"


class CreateType(str, Enum):
    file = "file"
    folder = "folder"
    collection = "collection"


class LinkDataOnly(str, Enum):
    copy_files = "copy_files"
    link_to_files = "link_to_files"


class ModelClass(str, Enum):
    LibraryDataset = "LibraryDataset"
    LibraryFolder = "LibraryFolder"


class LibraryContentsCreatePayload(Model):
    create_type: CreateType = Field(
        ...,
        title="the type of item to create",
    )
    upload_option: Optional[UploadOption] = Field(
        UploadOption.upload_file,
        title="the method to use for uploading files",
    )
    folder_id: LibraryFolderDatabaseIdField = Field(
        ...,
        title="the encoded id of the parent folder of the new item",
    )
    tag_using_filenames: Optional[bool] = Field(
        False,
        title="create tags on datasets using the file's original name",
    )
    tags: Optional[List[str]] = Field(
        [],
        title="create the given list of tags on datasets",
    )
    from_hda_id: Optional[DecodedDatabaseIdField] = Field(
        None,
        title="(only if create_type is 'file') the encoded id of an accessible HDA to copy into the library",
    )
    from_hdca_id: Optional[DecodedDatabaseIdField] = Field(
        None,
        title="(only if create_type is 'file') the encoded id of an accessible HDCA to copy into the library",
    )
    ldda_message: Optional[str] = Field(
        "",
        title="the new message attribute of the LDDA created",
    )
    extended_metadata: Optional[Union[Dict[str, Any], List[Any], int, float, str, bool]] = Field(
        None,
        title="sub-dictionary containing any extended metadata to associate with the item",
    )


class LibraryContentsFileCreatePayload(LibraryContentsCreatePayload):
    dbkey: Optional[Union[str, list]] = Field(
        "?",
        title="database key",
    )
    roles: Optional[str] = Field(
        "",
        title="user selected roles",
    )
    file_type: Optional[str] = Field(
        None,
        title="file type",
    )
    server_dir: Optional[str] = Field(
        "",
        title="(only if upload_option is 'upload_directory') relative path of the "
        "subdirectory of Galaxy ``library_import_dir`` (if admin) or "
        "``user_library_import_dir`` (if non-admin) to upload. "
        "All and only the files (i.e. no subdirectories) contained "
        "in the specified directory will be uploaded.",
    )
    filesystem_paths: Optional[str] = Field(
        "",
        title="(only if upload_option is 'upload_paths' and the user is an admin) "
        "file paths on the Galaxy server to upload to the library, one file per line",
    )
    link_data_only: Optional[LinkDataOnly] = Field(
        LinkDataOnly.copy_files,
        title="(only when upload_option is 'upload_directory' or 'upload_paths')."
        "Setting to 'link_to_files' symlinks instead of copying the files",
    )
    uuid: Optional[str] = Field(
        None,
        title="UUID of the dataset to upload",
    )


class LibraryContentsFolderCreatePayload(LibraryContentsCreatePayload):
    name: Optional[str] = Field(
        "",
        title="(only if create_type is 'folder') name of the folder to create",
    )
    description: Optional[str] = Field(
        "",
        title="(only if create_type is 'folder') description of the folder to create",
    )


class LibraryContentsCollectionCreatePayload(LibraryContentsCreatePayload):
    collection_type: str = Field(
        ...,
        title="the type of collection to create",
    )
    element_identifiers: List[Dict[str, Any]] = Field(
        ...,
        title="list of dictionaries containing the element identifiers for the collection",
    )
    name: Optional[str] = Field(
        None,
        title="the name of the collection",
    )
    hide_source_items: Optional[bool] = Field(
        False,
        title="if True, hide the source items in the collection",
    )
    copy_elements: Optional[bool] = Field(
        False,
        title="if True, copy the elements into the collection",
    )


class LibraryContentsUpdatePayload(Model):
    converted_dataset_id: Optional[DecodedDatabaseIdField] = Field(
        None,
        title="the decoded id of the dataset that was created from the file",
    )


class LibraryContentsDeletePayload(Model):
    purge: Optional[bool] = Field(
        False,
        title="if True, purge the library dataset",
    )


class LibraryContentsIndexResponse(Model):
    type: str
    name: str
    url: str


class LibraryContentsIndexFolderResponse(LibraryContentsIndexResponse):
    id: EncodedLibraryFolderDatabaseIdField


class LibraryContentsIndexDatasetResponse(LibraryContentsIndexResponse):
    id: EncodedDatabaseIdField


class LibraryContentsIndexListResponse(RootModel):
    root: List[Union[LibraryContentsIndexFolderResponse, LibraryContentsIndexDatasetResponse]]


class LibraryContentsShowResponse(Model):
    model_class: ModelClass
    name: str
    genome_build: Optional[str]
    update_time: str
    parent_library_id: EncodedDatabaseIdField


class LibraryContentsShowFolderResponse(LibraryContentsShowResponse):
    id: EncodedLibraryFolderDatabaseIdField
    parent_id: Optional[EncodedLibraryFolderDatabaseIdField]
    description: str
    item_count: int
    deleted: bool
    library_path: List[str]


class LibraryContentsShowDatasetResponse(LibraryContentsShowResponse):
    id: EncodedDatabaseIdField
    ldda_id: EncodedDatabaseIdField
    folder_id: EncodedLibraryFolderDatabaseIdField
    state: str
    file_name: str
    created_from_basename: str
    uploaded_by: str
    message: Optional[str]
    date_uploaded: str
    file_size: int
    file_ext: str
    data_type: str
    misc_info: str
    misc_blurb: str
    peek: Optional[str]
    uuid: str
    metadata_dbkey: str
    metadata_data_lines: int
    tags: TagCollection


class LibraryContentsCreateFolderResponse(Model):
    id: EncodedLibraryFolderDatabaseIdField
    name: str
    url: str


class LibraryContentsCreateFolderListResponse(RootModel):
    root: List[LibraryContentsCreateFolderResponse]


class LibraryContentsCreateDatasetResponse(Model):
    id: EncodedDatabaseIdField
    hda_ldda: str
    model_class: str
    name: str
    deleted: bool
    visible: bool
    state: str
    library_dataset_id: EncodedDatabaseIdField
    file_size: int
    file_name: str
    update_time: str
    file_ext: str
    data_type: str
    genome_build: str
    misc_info: str
    misc_blurb: str
    created_from_basename: str
    uuid: str
    parent_library_id: EncodedDatabaseIdField
    metadata_dbkey: str
    metadata_data_lines: int
    metadata_comment_lines: Union[str, int]
    metadata_columns: int
    metadata_column_types: List[str]
    metadata_column_names: List[str]
    metadata_delimiter: str


class LibraryContentsCreateDatasetListResponse(RootModel):
    root: List[LibraryContentsCreateDatasetResponse]


class LibraryContentsDeleteResponse(Model):
    pass
