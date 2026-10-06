"""Types for everything the collaboration server sends and receives.

The protocol grew as dictionaries passed between `astrocontrol.collab` and this
server. These models write down what those dictionaries already are, so that
FastAPI checks what arrives and publishes an OpenAPI document of the protocol
(`/openapi.json`, and `python tools/export_collab_api.py`).

They describe the wire, not new behaviour:

- Field names are the ones already sent, camelCase where the program uses it.
- Every model keeps fields it does not know (`extra="allow"`), so an older or
  newer program is never refused for sending one field more.
- Request bodies are read back with `model_dump(exclude_unset=True)`, and
  responses are returned with `response_model_exclude_unset=True`, so a model
  never adds a key that was not there before.

`astrocontrol.collab` still holds the rules and its dataclasses still do the
reading; these types are the published shape of their payloads.
"""
from __future__ import annotations

import math
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _number(value: Any) -> float | None:
    """As `astrocontrol.collab` reads a number: blank or unreadable is unknown."""
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _count(value: Any) -> int | None:
    """As `astrocontrol.collab` reads a whole number: unreadable is unknown."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


#: A number that may be unknown. Read leniently, as the program has always
#: read it, so a rig with a blank setting is not refused for it.
Number = Annotated[float | None, BeforeValidator(_number)]
#: A whole number that may be unknown, read the same way.
Count = Annotated[int | None, BeforeValidator(_count)]


class Wire(BaseModel):
    """A payload as it crosses the wire: known fields typed, others kept."""

    model_config = ConfigDict(extra="allow")


# ---------------------------------------------------------------------------
# Sky and rigs
# ---------------------------------------------------------------------------

class Region(Wire):
    """A rectangle of sky. Degrees throughout; `ra` is degrees, not hours.

    `width` and `height` are angles on the sky. `rotation` is the position
    angle contributing cameras should shoot at; the rectangle itself is
    north-up.
    """

    ra: float = Field(description="Right ascension of the centre, degrees.")
    dec: float = Field(description="Declination of the centre, degrees.")
    width: float = Field(description="Width on the sky, degrees.")
    height: float = Field(description="Height on the sky, degrees.")
    rotation: float = Field(default=0.0, description="Position angle to shoot at, degrees.")


class Cell(Region):
    """One cell of a rig's own tiling of a project, and where it sits."""

    row: int
    column: int


class RigProfile(Wire):
    """What a telescope is and what it achieves, sent with every hello."""

    name: str = ""
    focalLength: Number = Field(default=None, description="Millimetres.")
    pixelSize: Number = Field(default=None, description="Microns, unbinned.")
    sensorWidth: Count = Field(default=None, description="Pixels, unbinned.")
    sensorHeight: Count = Field(default=None, description="Pixels, unbinned.")
    binning: Count = 1
    filters: dict[str, Number] = Field(
        default_factory=dict, description="Filter name to bandpass in nm, or null if unknown.")
    colour: bool = Field(default=False, description="A one-shot colour camera.")
    rotation: Number = Field(
        default=None,
        description="Camera position angle in degrees when it cannot be turned; "
                    "null when a rotator can set any angle.")
    typicalHfr: Number = Field(default=None, description="Arcseconds.")
    typicalGuideRms: Number = Field(default=None, description="Arcseconds.")
    exposures: dict[str, Number] = Field(
        default_factory=dict,
        description="Sub length in seconds per filter: what the rig's darks are built for.")
    hoursPerNight: Number = Field(
        default=None, description="Hours a night the rig gives; null means as long as targets are up.")
    windowFrom: str = Field(default="", description='Local clock time, such as "21:00".')
    windowTo: str = Field(default="", description="Local clock time.")
    scale: Number = Field(default=None, description="Arcseconds per pixel, computed.")
    field: list[float] | None = Field(
        default=None, description="Field of view [width, height] in degrees, computed.")


class Presence(Wire):
    """Where a telescope points and what it is doing, as it chooses to say."""

    ra: Number = Field(default=None, description="Hours.")
    dec: Number = Field(default=None, description="Degrees.")
    state: str = ""
    target: str = ""
    project: str = ""
    telescope: str = Field(default="", description="What to call the telescope on the group's chart, such as its equipment profile's name.")


class TelescopePresence(Wire):
    """One telescope as the group sees it."""

    id: str
    name: str = Field(description="What the telescope says to call it, or the name it was enrolled under.")
    enrolledAs: str | None = Field(default=None, description="The name it was enrolled under.")
    owner: str
    ra: Number
    dec: Number
    state: str
    target: str
    project: str
    ageSeconds: int
    online: bool


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

class Requirements(Wire):
    """What a project will take. Star size and guiding are in arcseconds."""

    minFocalLength: Number = None
    maxFocalLength: Number = None
    minScale: Number = Field(default=None, description="Arcseconds per pixel.")
    maxScale: Number = Field(default=None, description="Arcseconds per pixel.")
    acceptColour: bool = True
    colourMaxMoon: Number = Field(
        default=None, description="Moon illumination (0-1) above which a colour camera's night is refused.")
    maxHfr: Number = Field(default=None, description="Mean star size over a night, arcseconds.")
    maxGuideRms: Number = Field(default=None, description="Mean guiding error, arcseconds.")
    minExposure: Number = Field(default=None, description="Seconds.")
    maxExposure: Number = Field(default=None, description="Seconds.")
    filters: dict[str, Number] = Field(
        default_factory=dict, description="Filters wanted, to the widest bandpass accepted in nm, or null for any.")
    maxMoonIllumination: Number = None
    minMoonSeparation: Number = Field(default=None, description="Degrees.")
    minAltitude: Number = Field(default=None, description="Degrees.")
    requireCalibrated: bool = False
    minFramesPerVisit: Count = Field(default=10, description="Fewest frames a visit to one panel is worth.")


class ProjectPayload(Wire):
    """A project's definition, as stored."""

    region: Region
    kind: Literal["single", "mosaic"] = "mosaic"
    requirements: Requirements = Field(default_factory=Requirements)
    goals: dict[str, float] = Field(
        default_factory=dict, description="Depth wanted at every point, per filter, in hours.")
    notes: str = ""


class Project(Wire):
    id: str
    name: str
    coordinator: str = ""
    owner_id: str = ""
    created: float
    status: Literal["open", "closed"] = "open"
    payload: ProjectPayload


class Compatibility(Wire):
    """Whether a rig meets a project's requirements, check by check."""

    class Check(Wire):
        check: str
        ok: bool | None
        detail: str

    ok: bool
    certain: bool
    checks: list[Check]
    summary: str


class FilterProgress(Wire):
    """How far one filter has got across the whole region."""

    goalHours: float
    atGoal: float = Field(description="Share of the region at (within a tenth of) the goal depth, 0-1.")
    average: float = Field(description="The region's depth against the goal, each point capped at the goal, 0-1.")
    thinnest: float = Field(description="The least-covered point's depth against the goal, 0-1.")


class OpenProject(Wire):
    """An open project as a telescope browsing for one sees it."""

    id: str
    name: str
    coordinator: str
    ownerId: str
    region: Region | dict[str, Any]
    kind: Literal["single", "mosaic"]
    requirements: Requirements
    goals: dict[str, float]
    notes: str
    compatibility: Compatibility
    joined: bool
    collected: dict[str, float] = Field(description="Accepted hours per filter.")
    participants: int
    participantsOnline: int
    participantNames: list[str]
    progress: dict[str, FilterProgress] | None = Field(default=None, description="Per filter, across everybody.")


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

class FilterTask(Wire):
    """One filter's share of a task."""

    filter: str
    exposure: float = Field(description="Sub length, seconds.")
    hours: float = Field(description="Depth wanted on each panel, hours.")


class Visit(Wire):
    """Tonight's slice of a task: how long on each panel, and in what."""

    seconds: Number = None
    frames: dict[str, int] = Field(default_factory=dict, description="Frames per filter on each panel tonight.")
    filter: str | None = Field(default=None, description="Tonight's one filter on a mosaic.")
    moon: Number = Field(default=None, description="How much the Moon spoiled the night the list was made for, 0-1.")


TaskState = Literal["offered", "accepted", "declined", "complete", "superseded"]


class Task(Wire):
    """A rig's share of a project: the whole region tiled with its own camera,
    and which of those cells are its to shoot tonight."""

    id: str
    project: str
    projectName: str = ""
    agent: str = ""
    region: Region
    filters: list[FilterTask] = Field(default_factory=list)
    state: TaskState = "offered"
    version: int = 1
    issued: float = 0.0
    note: str = ""
    seconds: Number = None
    cells: list[Cell] = Field(default_factory=list)
    share: list[int] = Field(default_factory=list, description="Indexes into `cells` to shoot tonight, in order.")
    kind: Literal["single", "mosaic"] = "mosaic"
    visit: Visit | dict[str, Any] | None = None
    assignedNight: str | None = None
    assignedAt: Number = None
    dealtHours: Number = None
    tiledRotation: Number = None


# ---------------------------------------------------------------------------
# What comes back
# ---------------------------------------------------------------------------

class Contribution(Wire):
    """One night's work on one filter and panel, as measured."""

    project: str = ""
    task: str = ""
    night: str = ""
    filterName: str = ""
    panel: str = ""
    frames: Count = 0
    seconds: Number = 0.0
    exposure: Number = Field(default=0.0, description="Sub length, seconds.")
    footprint: Region | None = Field(default=None, description="The solved footprint of the panel.")
    scale: Number = Field(default=None, description="Arcseconds per pixel.")
    focalLength: Number = None
    hfr: Number = Field(default=None, description="Mean star size over the night, arcseconds.")
    guideRms: Number = Field(default=None, description="Mean guiding error, arcseconds.")
    moonIllumination: Number = None
    moonSeparation: Number = Field(default=None, description="Degrees.")
    calibrated: bool = False
    bandpass: Number = Field(default=None, description="nm, of the filter used.")
    colour: bool = False


class Verdict(Wire):
    accepted: bool
    reasons: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    summary: str = ""
    overriddenBy: str | None = None
    overrideReason: str | None = None


class Recorded(Wire):
    id: str
    accepted: bool
    duplicate: bool
    verdict: Verdict


class ContributionRow(Wire):
    """A stored contribution, with its verdict."""

    id: str
    project: str
    agent: str
    task: str = ""
    night: str = ""
    filter: str = ""
    panel: str = ""
    seconds: float = 0.0
    accepted: bool
    overridden: bool = False
    received: float
    payload: Contribution
    verdict: Verdict | dict[str, Any]


class Agent(Wire):
    """An enrolled telescope, without its token."""

    id: str
    name: str
    owner: str = ""
    owner_id: str = ""
    created: float
    seen: float = 0.0
    profile: RigProfile | dict[str, Any] = Field(default_factory=dict)
    presence: Presence | dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

class HelloRequest(Wire):
    """A telescope saying what it is and, if it likes, where it points."""

    protocol: int = 1
    profile: RigProfile = Field(default_factory=RigProfile)
    presence: Presence | None = None


class TaskStateRequest(Wire):
    state: Literal["accepted", "declined", "complete"]


class ReportRequest(Wire):
    """One night's work: one record per filter and panel."""

    contributions: list[Contribution] = Field(default_factory=list, max_length=200)


class JoinRequest(Wire):
    """Signing up for a share of a project."""

    hours: float = Field(default=0.0, ge=0.0, le=24.0,
                         description="Hours per filter, capped by the project's goal; 0 takes the goal.")
    exposure: float = Field(default=0.0, ge=0.0, le=3600.0,
                            description="Sub length for a filter with no entry in `exposures`; 0 takes the middle of the project's range.")
    exposures: dict[str, float] = Field(default_factory=dict, description="The rig's own sub length per filter.")
    night: str = Field(default="", max_length=16,
                       description="The night the rig is in, so the first deal is tonight's.")
    moon: float | None = Field(default=None, ge=0.0, le=1.0,
                               description="How much of the Moon is lit tonight, 0-1.")
    moonUp: float | None = Field(default=None, ge=0.0, le=1.0,
                                 description="The fraction of the dark hours the Moon is up, 0-1.")


class AgentRequest(Wire):
    name: str = Field(min_length=1, max_length=80)
    owner: str = Field(default="", max_length=80)


class ProjectRequest(Wire):
    name: str = Field(min_length=1, max_length=120)
    coordinator: str = Field(default="", max_length=80)
    region: Region
    kind: Literal["single", "mosaic"] = "mosaic"
    requirements: Requirements = Field(default_factory=Requirements)
    goals: dict[str, float] = Field(default_factory=dict, description="Hours per filter at every point.")
    notes: str = Field(default="", max_length=2000)


class ProjectUpdateRequest(Wire):
    """Changing a project after it was started. Every field is optional."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    region: Region | None = None
    kind: Literal["single", "mosaic"] | None = None
    requirements: Requirements | None = None
    goals: dict[str, float] | None = None
    notes: str | None = Field(default=None, max_length=2000)
    status: Literal["open", "closed"] | None = None


class TaskRequest(Wire):
    agent: str
    region: Region
    filters: list[FilterTask] = Field(default_factory=list, max_length=20)
    note: str = Field(default="", max_length=500)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class HelloResponse(Wire):
    agent: str
    name: str
    protocol: int
    serverTime: float


class PresenceResponse(Wire):
    telescopes: list[TelescopePresence]
    online: int
    people: int
    onlineSeconds: int
    serverTime: float


class TaskResponse(Wire):
    """What a telescope should be shooting: every share it holds."""

    task: Task | None
    tasks: list[Task]
    requirementsByProject: dict[str, Requirements] | None = None
    version: int
    protocol: int
    requirements: Requirements | None = None


class DepthCell(Wire):
    ra: float
    dec: float
    width: float
    height: float
    row: int
    column: int


class DepthMap(Wire):
    """Everybody's accepted seconds on every cell of a fine grid over the region, per filter."""

    project: str
    name: str
    region: Region
    columns: int
    rows: int
    cells: list[DepthCell]
    seconds: dict[str, list[float]] = Field(description="Per filter, seconds on each cell, in the order of `cells`.")
    goals: dict[str, float] = Field(description="Hours wanted per filter at every point.")
    progress: dict[str, FilterProgress]


class OpenProjects(Wire):
    projects: list[OpenProject]
    protocol: int


class JoinResponse(Wire):
    task: Task | None
    requirements: Requirements
    alreadyJoined: bool | None = None


class TaskEnvelope(Wire):
    task: Task


class ReportResponse(Wire):
    recorded: list[Recorded]


class AgentCreated(Wire):
    agent: Agent
    token: str = Field(description="Shown once. Keep it on the telescope it is for.")


class AgentList(Wire):
    agents: list[Agent]


class ProjectEnvelope(Wire):
    project: Project | None


class ProjectList(Wire):
    projects: list[Project]


class ProjectDetail(Wire):
    project: Project
    tasks: list[Task]
    contributions: list[ContributionRow]


class ContributionEnvelope(Wire):
    contribution: ContributionRow | None


class AuthStatus(Wire):
    discord: bool
    guild: str
    roleRequired: bool
    publicUrl: str


class LoginStarted(Wire):
    code: str
    url: str
    expiresIn: int


class SignedInUser(Wire):
    id: str
    name: str
    avatar: str = ""
    admin: bool
    canStart: bool


class LoginPoll(Wire):
    state: Literal["pending", "done", "claimed", "expired"]
    token: str | None = None
    user: SignedInUser | None = None


class Me(Wire):
    id: str
    name: str
    admin: bool
    canStart: bool


class SignedOut(Wire):
    signedOut: bool


class Health(Wire):
    ok: bool
    protocol: int
    time: float
    version: str
    adminConfigured: bool
    discord: bool
    roleRequired: bool
    features: list[str] = Field(
        default_factory=list, description='Optional parts offered, such as "signin".')
