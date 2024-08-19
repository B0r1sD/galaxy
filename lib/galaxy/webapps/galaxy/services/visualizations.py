import json
import logging
from typing import (
    Tuple,
    Union,
)

from galaxy import exceptions
from galaxy.managers.base import (
    is_valid_slug,
    security_check,
)
from galaxy.managers.context import ProvidesAppContext
from galaxy.managers.sharable import (
    slug_exists,
    SlugBuilder,
)
from galaxy.managers.visualizations import (
    VisualizationManager,
    VisualizationSerializer,
)
from galaxy.model import (
    Visualization,
    VisualizationRevision,
)
from galaxy.model.base import transaction
from galaxy.model.item_attrs import (
    add_item_annotation,
    get_item_annotation_str,
)
from galaxy.schema.fields import DecodedDatabaseIdField
from galaxy.schema.visualization import (
    VisualizationCreatePayload,
    VisualizationCreateResponse,
    VisualizationIndexQueryPayload,
    VisualizationRevisionResponse,
    VisualizationShowResponse,
    VisualizationSummaryList,
    VisualizationUpdatePayload,
    VisualizationUpdateResponse,
)
from galaxy.security.idencoding import IdEncodingHelper
from galaxy.util.hash_util import md5_hash_str
from galaxy.util.sanitize_html import sanitize_html
from galaxy.web import url_for
from galaxy.webapps.galaxy.services.base import ServiceBase
from galaxy.webapps.galaxy.services.notifications import NotificationService
from galaxy.webapps.galaxy.services.sharable import ShareableService

log = logging.getLogger(__name__)


class VisualizationsService(ServiceBase):
    """Common interface/service logic for interactions with visualizations in the context of the API.

    Provides the logic of the actions invoked by API controllers and uses type definitions
    and pydantic models to declare its parameters and return types.
    """

    def __init__(
        self,
        security: IdEncodingHelper,
        manager: VisualizationManager,
        serializer: VisualizationSerializer,
        notification_service: NotificationService,
    ):
        super().__init__(security)
        self.manager = manager
        self.serializer = serializer
        self.shareable_service = ShareableService(self.manager, self.serializer, notification_service)

    # TODO: add the rest of the API actions here and call them directly from the API controller

    def index(
        self,
        trans,
        payload: VisualizationIndexQueryPayload,
        include_total_count: bool = False,
    ) -> Tuple[VisualizationSummaryList, int]:
        """Return a list of Visualizations viewable by the user

        :rtype:     list
        :returns:   dictionaries containing Visualization details
        """
        if not trans.user_is_admin:
            user_id = trans.user and trans.user.id
            if payload.user_id and payload.user_id != user_id:
                raise exceptions.AdminRequiredException("Only admins can index the visualizations of others")

        entries, total_matches = self.manager.index_query(trans, payload, include_total_count)
        return (
            VisualizationSummaryList(root=[entry.to_dict() for entry in entries]),
            total_matches,
        )

    def show(
        self,
        trans: ProvidesAppContext,
        visualization_id: DecodedDatabaseIdField,
    ) -> VisualizationShowResponse:
        """Return a dictionary containing the Visualization's details

        :rtype:     dictionary
        :returns:   Visualization details
        """
        # TODO: revisions should be a contents/nested controller like viz/xxx/r/xxx)?
        # the important thing is the config
        # TODO:?? /api/visualizations/registry -> json of registry.listings?
        visualization = self._get_visualization(trans, visualization_id, check_ownership=False, check_accessible=True)
        dictionary = {
            "model_class": "Visualization",
            "id": visualization.id,
            "title": visualization.title,
            "type": visualization.type,
            "user_id": visualization.user.id,
            "dbkey": visualization.dbkey,
            "slug": visualization.slug,
            # to_dict only the latest revision (allow older to be fetched elsewhere)
            "latest_revision": self._get_visualization_revision_dict(visualization.latest_revision),
            # need to encode ids in revisions as well
            # NOTE: does not encode ids inside the configs
            "revisions": [r.id for r in visualization.revisions],
        }
        # replace with trans.url_builder if possible
        dictionary["url"] = url_for(
            controller="visualization",
            action="display_by_username_and_slug",
            username=visualization.user.username,
            slug=visualization.slug,
        )
        dictionary["username"] = visualization.user.username
        dictionary["email_hash"] = md5_hash_str(visualization.user.email)
        dictionary["tags"] = visualization.make_tag_string_list()
        dictionary["annotation"] = get_item_annotation_str(trans.sa_session, trans.user, visualization)
        if trans.app.visualizations_registry:
            dictionary["plugin"] = trans.app.visualizations_registry.get_plugin(dictionary["type"]).to_dict()
        return VisualizationShowResponse(**dictionary)

    def create(
        self,
        trans: ProvidesAppContext,
        payload: VisualizationCreatePayload,
    ) -> VisualizationCreateResponse:
        """Returns a dictionary of the created visualization

        :rtype:     dictionary
        :returns:   dictionary containing Visualization details
        """

        if payload.import_id:
            visualization = self._import_visualization(trans, payload.import_id)
        else:
            payload = self._validate_and_parse_payload(payload)
            # must have a type (I've taken this to be the visualization name)
            if not payload.type:
                raise exceptions.RequestParameterMissingException("key/value 'type' is required")
            type = payload.type
            title = payload.title
            slug = payload.slug
            dbkey = payload.dbkey
            annotation = payload.annotation
            config = payload.config
            save = payload.save

            # generate defaults - this will err if given a weird key?
            visualization = self._create_visualization(trans, title, type, dbkey, slug, annotation, save)

            # Create and save first visualization revision
            revision = trans.model.VisualizationRevision(
                visualization=visualization, title=title, config=config, dbkey=dbkey
            )
            visualization.latest_revision = revision

            if save:
                session = trans.sa_session
                session.add(revision)
                with transaction(session):
                    session.commit()

        rval = {"id": visualization.id}

        return VisualizationCreateResponse(**rval)

    def update(
        self,
        trans: ProvidesAppContext,
        visualization_id: DecodedDatabaseIdField,
        payload: VisualizationUpdatePayload,
    ) -> Union[VisualizationUpdateResponse, None]:
        """
        Update a visualization

        :rtype:     dictionary
        :returns:   dictionary containing Visualization details
        """
        rval = None
        payload = self._validate_and_parse_payload(payload)

        # there's a differentiation here between updating the visualization and creating a new revision
        # that needs to be handled clearly here or alternately, using a different controller
        # like e.g. PUT /api/visualizations/{visualization_id}/r/{revision_id}

        # TODO: consider allowing direct alteration of revisions title (without a new revision)
        #   only create a new revsion on a different config

        # only update owned visualizations
        visualization = self._get_visualization(trans, visualization_id, check_ownership=True)
        title = payload.title or visualization.latest_revision.title
        dbkey = payload.dbkey or visualization.latest_revision.dbkey
        deleted = payload.deleted or visualization.deleted
        config = payload.config or visualization.latest_revision.config

        latest_config = visualization.latest_revision.config
        if (
            (title != visualization.latest_revision.title)
            or (dbkey != visualization.latest_revision.dbkey)
            or (json.dumps(config) != json.dumps(latest_config))
        ):
            revision = self._add_visualization_revision(trans, visualization, config, title, dbkey)
            rval = {"id": visualization_id, "revision": revision.id}

        # allow updating vis title
        visualization.title = title
        visualization.deleted = deleted
        with transaction(trans.sa_session):
            trans.sa_session.commit()

        return VisualizationUpdateResponse(**rval) if rval else None

    def _validate_and_parse_payload(
        self,
        payload: Union[VisualizationCreatePayload, VisualizationUpdatePayload],
    ) -> Union[VisualizationCreatePayload, VisualizationUpdatePayload]:
        """
        Validate and parse incomming data payload for a visualization.
        """
        # This layer handles (most of the stricter idiot proofing):
        #   - unknown/unallowed keys
        #   - changing data keys from api key to attribute name
        #   - protection against bad data form/type
        #   - protection against malicious data content
        # all other conversions and processing (such as permissions, etc.) should happen down the line

        # keys listed here don't error when attempting to set, but fail silently
        #   this allows PUT'ing an entire model back to the server without attribute errors on uneditable attrs
        valid_but_uneditable_keys = (
            "id",
            "model_class",
            # TODO: fill out when we create to_dict, get_dict, whatevs
        )
        # TODO: importable
        ValidationError = exceptions.RequestParameterInvalidException

        validated_payload = {}
        for key, val in payload.model_dump().items():
            # By adding the pydatnic model there will be some variables that are not set and should be ignored in the validation
            if val is None:
                continue
            # TODO: validate types in VALID_TYPES/registry names at the mixin/model level?
            if key == "type":
                if not isinstance(val, str):
                    raise ValidationError(f"{key} must be a string or unicode: {str(type(val))}")
                val = sanitize_html(val)
            elif key == "config":
                if not isinstance(val, dict):
                    raise ValidationError(f"{key} must be a dictionary: {str(type(val))}")
            elif key == "annotation":
                if not isinstance(val, str):
                    raise ValidationError(f"{key} must be a string or unicode: {str(type(val))}")
                val = sanitize_html(val)
            elif key == "deleted":
                if not isinstance(val, bool):
                    raise ValidationError(f"{key} must be a bool: {str(type(val))}")

            # these are keys that actually only be *updated* at the revision level and not here
            #   (they are still valid for create, tho)
            elif key == "title":
                if not isinstance(val, str):
                    raise ValidationError(f"{key} must be a string or unicode: {str(type(val))}")
                val = sanitize_html(val)
            elif key == "slug":
                if not isinstance(val, str):
                    raise ValidationError(f"{key} must be a string: {str(type(val))}")
                val = sanitize_html(val)
            elif key == "dbkey":
                if not isinstance(val, str):
                    raise ValidationError(f"{key} must be a string or unicode: {str(type(val))}")
                val = sanitize_html(val)

            elif key not in valid_but_uneditable_keys:
                continue
                # raise AttributeError( 'unknown key: %s' %( str( key ) ) )

            validated_payload[key] = val
        if isinstance(payload, VisualizationCreatePayload):
            return VisualizationCreatePayload(**validated_payload)
        elif isinstance(payload, VisualizationUpdatePayload):
            return VisualizationUpdatePayload(**validated_payload)

    def _get_visualization(
        self,
        trans: ProvidesAppContext,
        visualization_id: DecodedDatabaseIdField,
        check_ownership=True,
        check_accessible=False,
    ) -> Visualization:
        """
        Get a Visualization from the database by id, verifying ownership.
        """
        # Load workflow from database
        try:
            visualization = trans.sa_session.get(Visualization, visualization_id)
        except TypeError:
            visualization = None
        if not visualization:
            raise exceptions.ObjectNotFound("Visualization not found")
        else:
            return security_check(trans, visualization, check_ownership, check_accessible)

    def _get_visualization_revision_dict(
        self,
        revision: VisualizationRevision,
    ) -> VisualizationRevisionResponse:
        """
        Return a set of detailed attributes for a visualization in dictionary form.
        NOTE: that encoding ids isn't done here should happen at the caller level.
        """
        revision_dict = {
            "model_class": "VisualizationRevision",
            "id": revision.id,
            "visualization_id": revision.visualization.id,
            "title": revision.title,
            "dbkey": revision.dbkey,
            "config": revision.config,
        }
        return VisualizationRevisionResponse(**revision_dict)

    def _add_visualization_revision(
        self,
        trans: ProvidesAppContext,
        visualization: Visualization,
        config: dict,
        title: str,
        dbkey: str,
    ) -> VisualizationRevision:
        """
        Adds a new `VisualizationRevision` to the given `visualization` with
        the given parameters and set its parent visualization's `latest_revision`
        to the new revision.
        """
        # precondition: only add new revision on owned vis's
        # TODO:?? should we default title, dbkey, config? to which: visualization or latest_revision?
        revision = trans.model.VisualizationRevision(
            visualization=visualization, title=title, dbkey=dbkey, config=config
        )

        visualization.latest_revision = revision
        # TODO:?? does this automatically add revision to visualzation.revisions?
        trans.sa_session.add(revision)
        with transaction(trans.sa_session):
            trans.sa_session.commit()
        return revision

    def _create_visualization(
        self,
        trans: ProvidesAppContext,
        title: str,
        type: str,
        dbkey: str = None,
        slug: str = None,
        annotation: str = None,
        save: bool = True,
    ) -> Visualization:
        """Create visualization but not first revision. Returns Visualization object."""
        user = trans.get_user()

        # Error checking.
        title_err = slug_err = ""
        if not title:
            title_err = "visualization name is required"
        elif slug and not is_valid_slug(slug):
            slug_err = "visualization identifier must consist of only lowercase letters, numbers, and the '-' character"
        elif slug and slug_exists(trans.sa_session, trans.model.Visualization, user, slug, ignore_deleted=True):
            slug_err = "visualization identifier must be unique"

        if title_err or slug_err:
            # TODO: handle this error structure better
            val_err = str(title_err or slug_err)
            raise exceptions.RequestParameterMissingException(val_err)

        # Create visualization
        visualization = trans.model.Visualization(user=user, title=title, dbkey=dbkey, type=type)
        if slug:
            visualization.slug = slug
        else:
            slug_builder = SlugBuilder()
            slug_builder.create_item_slug(trans.sa_session, visualization)
        if annotation:
            annotation = sanitize_html(annotation)
            # TODO: if this is to stay in the mixin, UsesAnnotations should be added to the superclasses
            #   right now this is depending on the classes that include this mixin to have UsesAnnotations
            add_item_annotation(trans.sa_session, trans.user, visualization, annotation)

        if save:
            session = trans.sa_session
            session.add(visualization)
            with transaction(session):
                session.commit()

        return visualization

    def _import_visualization(
        self,
        trans: ProvidesAppContext,
        visualization_id: DecodedDatabaseIdField,
    ) -> Visualization:
        """
        Copy the visualization with the given id and associate the copy
        with the given user (defaults to trans.user).

        Raises `ItemAccessibilityException` if `user` is not passed and
        the current user is anonymous, and if the visualization is not `importable`.
        Raises `ItemDeletionException` if the visualization has been deleted.
        """
        # default to trans.user, error if anon
        if not trans.user:
            raise exceptions.ItemAccessibilityException("You must be logged in to import Galaxy visualizations")
        user = trans.user

        # check accessibility
        visualization = self._get_visualization(trans, visualization_id, check_ownership=False)
        if not visualization.importable:
            raise exceptions.ItemAccessibilityException(
                "The owner of this visualization has disabled imports via this link."
            )
        if visualization.deleted:
            raise exceptions.ItemDeletionException("You can't import this visualization because it has been deleted.")

        # copy vis and alter title
        # TODO: need to handle custom db keys.
        imported_visualization = visualization.copy(user=user, title=f"imported: {visualization.title}")
        trans.sa_session.add(imported_visualization)
        with transaction(trans.sa_session):
            trans.sa_session.commit()
        return imported_visualization
