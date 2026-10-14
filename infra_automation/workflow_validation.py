"""Bounded, effect-free parsing and typed substitution for workflow major 2.

Parsing alone is private: a typed shape has not passed graph/lineage validation.
No resolution result establishes execution permission or predecessor success.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import heapq
import json
import re
from typing import Any, cast

from pydantic import ValidationError
import yaml
from yaml.events import (
    AliasEvent,
    CollectionStartEvent,
    CollectionEndEvent,
    DocumentStartEvent,
)
from yaml.nodes import MappingNode

from infra_automation.contracts import (
    SAFE_INTEGER,
    STEP_CONTRACTS,
    ClosedModel,
    Identifier,
    OutputKind,
    RegistryContract,
    ValidationLimits,
)
from infra_automation.workflow_schema import (
    Workflow,
    IntegerInput,
    StringInput,
    InputReference,
    ProjectReference,
    RunReference,
    StepReference,
    AdmittedCollectionStep,
    UploadedIntakeStep,
    PolicyEvaluationStep,
    RegisteredGithubHandoffStep,
    HumanDecisionStep,
    SharedAnalysisStep,
    Step,
)

_MESSAGES = {
    "invalid_input": "Input does not satisfy the validation interface.",
    "resource_limit": "Input exceeds a configured resource limit.",
    "yaml_syntax": "Definition contains invalid YAML syntax.",
    "yaml_duplicate_key": "Duplicate mapping keys are forbidden.",
    "yaml_key_type": "Mapping keys must be strings.",
    "yaml_feature_forbidden": "Definition uses a forbidden YAML feature.",
    "schema_version": "Workflow major version must be the strict integer 2.",
    "schema_field": "Definition does not satisfy the closed workflow schema.",
    "scope_unsupported": "Definition is outside the supported Tier 0/1 workflow scope.",
    "dependency_invalid": "A dependency is invalid.",
    "graph_cycle": "Dependencies contain a cycle.",
    "reference_invalid": "Reference does not identify an available declared value.",
    "reference_type": "Reference type or declared bounds do not match the field.",
    "binding_mismatch": "Authorization lineage does not have matching bindings.",
    "profile_unsupported": "Collection profile or authorization kind is not admitted.",
    "input_value_invalid": "Supplied input values do not satisfy their declarations.",
    "metadata_mismatch": "Supplied metadata does not match the definition scope.",
    "output_invalid": "Supplied outputs do not satisfy the producer contracts.",
}
_FIELDS = frozenset(
    "workflow_version project_id workspace_id environment inputs steps id kind depends_on source parameters max_artifact_bytes timeout_seconds repository_id commit_sha profile_digest limitation artifact report target_id authorization_kind binding decision ref name step_id output type required default max_length minimum maximum field profiles digest tool authorization_kinds handle".split()
)


@dataclass(frozen=True)
class Diagnostic:
    code: str
    message: str
    path: tuple[str | int, ...] = ()
    step_index: int | None = None
    line: int | None = None
    column: int | None = None


def _safe_path(path: tuple[Any, ...]) -> tuple[str | int, ...]:
    result: list[str | int] = []
    for position, part in enumerate(path):
        # Pydantic union alternatives are implementation labels, not wire fields.
        if (
            (
                position == 2
                and path[0] == "steps"
                and type(path[1]) is int
                and part in STEP_CONTRACTS
            )
            or (
                position == 2
                and path[0] == "inputs"
                and part in ("identifier", "commit_sha", "string", "integer", "boolean")
            )
            or (
                position > 0
                and path[position - 1]
                in (
                    "environment",
                    "target_id",
                    "repository_id",
                    "commit_sha",
                    "max_artifact_bytes",
                    "timeout_seconds",
                    "default",
                )
                and part
                in (
                    "constrained-str",
                    "constrained-int",
                    "str",
                    "int",
                    "bool",
                    "InputReference",
                    "input",
                    "project",
                    "run",
                )
            )
        ):
            continue
        if len(result) == 20:
            break
        if result and result[-1] == "inputs":
            result.append("<input>")
        elif type(part) is int and 0 <= part <= 131072:
            result.append(part)
        elif type(part) is str and part in _FIELDS:
            result.append(part)
        else:
            result.append("<unknown>")
    return tuple(result)


class IssueCollector:
    def __init__(self, max_errors: int = 50):
        if type(max_errors) is not int or not 1 <= max_errors <= 50:
            raise ValueError("Invalid diagnostic limit.")
        self.max_errors = max_errors
        self._errors: list[Diagnostic] = []
        self.truncated = False

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(self._errors)

    @property
    def has_errors(self) -> bool:
        return bool(self._errors)

    def add(
        self,
        code: str,
        path: tuple[Any, ...] = (),
        *,
        step_index: int | None = None,
        line: int | None = None,
        column: int | None = None,
    ) -> None:
        if len(self._errors) >= self.max_errors:
            self.truncated = True
            return
        safe = _safe_path(path)
        if (
            step_index is None
            and len(safe) > 1
            and safe[0] == "steps"
            and type(safe[1]) is int
        ):
            step_index = safe[1]
        self._errors.append(
            Diagnostic(
                code,
                _MESSAGES[code],
                safe,
                step_index
                if type(step_index) is int and 0 <= step_index <= 49
                else None,
                line if type(line) is int and 1 <= line <= 131073 else None,
                column if type(column) is int and 1 <= column <= 131073 else None,
            )
        )


class _ParseFailure(Exception):
    def __init__(self, code: str, mark: Any = None):
        self.code = code
        self.mark = mark


class _BoundedLoader(yaml.SafeLoader):
    def fetch_directive(self) -> None:
        # The scanner reaches this only for a directive, never quoted data.
        raise _ParseFailure("yaml_feature_forbidden", self.get_mark())

    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[str, Any]:
        result = {}
        for key_node, value_node in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                raise _ParseFailure("yaml_feature_forbidden", key_node.start_mark)
            if key_node.tag != "tag:yaml.org,2002:str":
                raise _ParseFailure("yaml_key_type", key_node.start_mark)
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise _ParseFailure("yaml_duplicate_key", key_node.start_mark)
            # Check duplicates before constructing the duplicate child.
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _string(loader: _BoundedLoader, node: Any) -> str:
    value = loader.construct_scalar(node)
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise _ParseFailure("yaml_feature_forbidden", node.start_mark)
    return value


def _integer(loader: _BoundedLoader, node: Any) -> int:
    token = loader.construct_scalar(node).replace("_", "")
    sign = -1 if token.startswith("-") else 1
    token = token.lstrip("+-")
    base = 10
    if token.startswith(("0x", "0b")):
        base = 16 if token[1] == "x" else 2
        token = token[2:]
    elif len(token) > 1 and token[0] == "0":
        base = 8
    value = 0
    if ":" in token:
        for component in token.split(":"):
            part = 0
            for char in component:
                part = part * 10 + ord(char) - ord("0")
                if part > SAFE_INTEGER:
                    raise _ParseFailure("resource_limit", node.start_mark)
            value = value * 60 + part
            if value > SAFE_INTEGER:
                raise _ParseFailure("resource_limit", node.start_mark)
    else:
        for char in token.lower():
            digit = ord(char) - ord("0") if char <= "9" else ord(char) - ord("a") + 10
            value = value * base + digit
            if value > SAFE_INTEGER:
                raise _ParseFailure("resource_limit", node.start_mark)
    return sign * value


def _forbidden_scalar(loader: _BoundedLoader, node: Any) -> Any:
    raise _ParseFailure("yaml_feature_forbidden", node.start_mark)


_BoundedLoader.add_constructor("tag:yaml.org,2002:str", _string)
_BoundedLoader.add_constructor("tag:yaml.org,2002:int", _integer)
_BoundedLoader.add_constructor("tag:yaml.org,2002:float", _forbidden_scalar)
_BoundedLoader.add_constructor("tag:yaml.org,2002:timestamp", _forbidden_scalar)


def _decode_json(text: str, max_depth: int) -> tuple[bool, Any]:
    """Preserve JSON scalar semantics without widening the YAML parsing budget."""
    depth = 0
    quoted = escaped = False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > max_depth:
                # Single-quoted/plain YAML may contain these characters as data.
                # Its event preflight decides the real depth before construction.
                return False, None
        elif char in "]}":
            depth -= 1

    failure: str | None = None
    non_json = False

    def integer(token: str) -> int:
        nonlocal failure
        digits = token.removeprefix("-").lstrip("0") or "0"
        maximum = str(SAFE_INTEGER)
        if len(digits) > len(maximum) or (
            len(digits) == len(maximum) and digits > maximum
        ):
            failure = failure or "resource_limit"
            return 0
        return int(token)

    def floating(token: str) -> None:
        nonlocal failure
        failure = failure or "yaml_feature_forbidden"

    def constant(token: str) -> None:
        nonlocal non_json
        # NaN/Infinity are JSONDecoder extensions, but can be plain YAML strings.
        non_json = True

    def mapping(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        nonlocal failure
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                failure = failure or "yaml_duplicate_key"
            result[key] = value
        return result

    try:
        data = json.loads(
            text,
            parse_int=integer,
            parse_float=floating,
            parse_constant=constant,
            object_pairs_hook=mapping,
        )
    except json.JSONDecodeError:
        return False, None
    if non_json:
        return False, None
    # Defer policy failures until complete JSON syntax is established; an invalid
    # JSON prefix may still be a supported YAML flow mapping.
    if failure:
        raise _ParseFailure(failure)
    pending = [data]
    while pending:
        value = pending.pop()
        if type(value) is dict:
            pending.extend(value.keys())
            pending.extend(value.values())
        elif type(value) is list:
            pending.extend(value)
        elif type(value) is str and any(
            0xD800 <= ord(char) <= 0xDFFF for char in value
        ):
            raise _ParseFailure("yaml_feature_forbidden")
    return True, data


def _parse_definition(
    raw: bytes, limits: ValidationLimits, issues: IssueCollector
) -> Workflow | None:
    try:
        if type(raw) is not bytes or type(limits) is not ValidationLimits:
            issues.add("invalid_input")
            return None
        try:
            limits = ValidationLimits.model_validate(
                limits.model_dump(warnings="error")
            )
        except (ValidationError, ValueError):
            issues.add("invalid_input")
            return None
        if len(raw) > limits.max_bytes:
            issues.add("resource_limit")
            return None
        text = raw.decode("utf-8", errors="strict")
        is_json, data = _decode_json(text, limits.max_depth)
        if not is_json:
            data = _decode_yaml(text, limits.max_depth)
        return _parse_model(data, limits, issues)
    except UnicodeError:
        issues.add("invalid_input")
    except _ParseFailure as exc:
        mark = exc.mark
        issues.add(
            exc.code,
            line=mark.line + 1 if mark else None,
            column=mark.column + 1 if mark else None,
        )
    except ValidationError as exc:
        for error in exc.errors(
            include_url=False, include_context=False, include_input=False
        ):
            issues.add("schema_field", tuple(error["loc"]))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        issues.add(
            "yaml_syntax",
            line=mark.line + 1 if mark else None,
            column=mark.column + 1 if mark else None,
        )
    except Exception:
        # Never relay parser/Pydantic exception messages or submitted values.
        issues.add("invalid_input")
    return None


def _decode_yaml(text: str, max_depth: int) -> Any:
    events = yaml.parse(text, Loader=_BoundedLoader)
    depth = documents = 0
    try:
        for event in events:
            if (
                isinstance(event, AliasEvent)
                or getattr(event, "anchor", None) is not None
                or getattr(event, "tag", None) is not None
            ):
                raise _ParseFailure("yaml_feature_forbidden", event.start_mark)
            if isinstance(event, DocumentStartEvent):
                documents += 1
                if documents > 1 or event.version is not None or event.tags:
                    raise _ParseFailure("yaml_feature_forbidden", event.start_mark)
            if isinstance(event, CollectionStartEvent):
                depth += 1
                if depth > max_depth:
                    raise _ParseFailure("resource_limit", event.start_mark)
            elif isinstance(event, CollectionEndEvent):
                depth -= 1
    finally:
        events.close()
    loader = _BoundedLoader(text)
    try:
        data = loader.get_single_data()
    finally:
        loader.dispose()
    return data


def _parse_model(
    data: Any, limits: ValidationLimits, issues: IssueCollector
) -> Workflow | None:
    if type(data) is not dict:
        issues.add("schema_field")
        return None
    if type(data.get("workflow_version")) is not int or data["workflow_version"] != 2:
        issues.add("schema_version", ("workflow_version",))
    for key, ceiling in [
        ("steps", limits.max_steps),
        ("inputs", limits.max_inputs),
    ]:
        if type(data.get(key)) in (dict, list) and len(data[key]) > ceiling:
            issues.add("resource_limit", (key,))
    if issues.has_errors:
        return None
    forbidden = {
        "when",
        "finally",
        "failure",
        "on_failure",
        "script",
        "plugin",
        "auto_approve",
        "continue_on_error",
        "loops",
        "loop",
        "apply",
        "destroy",
        "remediation",
        "execution_profile",
    }
    for key in data.keys() & forbidden:
        issues.add("scope_unsupported", (key,))
    if type(data.get("steps")) is list:
        for index, step in enumerate(data["steps"]):
            if type(step) is not dict:
                continue
            if type(step.get("kind")) is str and step["kind"] not in STEP_CONTRACTS:
                issues.add("scope_unsupported", ("steps", index, "kind"))
            for key in step.keys() & forbidden:
                issues.add("scope_unsupported", ("steps", index, key))
    if issues.has_errors:
        return None
    return Workflow.model_validate(data)


def normalize_identifier(value: Any, workflow: Workflow) -> str | InputReference | None:
    if type(value) in (str, InputReference):
        return value
    if type(value) is ProjectReference:
        return workflow.project_id if value.field == "id" else workflow.workspace_id
    if type(value) is RunReference:
        return getattr(workflow, value.field)
    return None


def _validate_scalar_references(
    workflow: Workflow, registry: RegistryContract, issues: IssueCollector
) -> None:
    def check(
        value: Any, expected: str, path: tuple[Any, ...], maximum: int | None = None
    ) -> None:
        if type(value) is InputReference:
            declaration = workflow.inputs.get(value.name)
            if declaration is None:
                issues.add("reference_invalid", path)
            elif declaration.type != expected or (
                maximum is not None
                and (
                    not isinstance(declaration, IntegerInput)
                    or not 1 <= declaration.minimum <= declaration.maximum <= maximum
                )
            ):
                issues.add("reference_type", path)
        elif type(value) in (ProjectReference, RunReference):
            normalized = normalize_identifier(value, workflow)
            if normalized is None:
                issues.add("scope_unsupported", path)
            elif type(normalized) is InputReference:
                check(normalized, expected, path)

    check(workflow.environment, "identifier", ("environment",))
    admitted = {profile.digest for profile in registry.profiles}
    for index, step in enumerate(workflow.steps):
        path = ("steps", index)
        if isinstance(step, (UploadedIntakeStep, AdmittedCollectionStep)):
            check(
                step.parameters.timeout_seconds,
                "integer",
                path + ("parameters", "timeout_seconds"),
                600,
            )
            check(
                step.parameters.max_artifact_bytes,
                "integer",
                path + ("parameters", "max_artifact_bytes"),
                8388608,
            )
        if type(step) is AdmittedCollectionStep:
            check(
                step.source.repository_id,
                "identifier",
                path + ("source", "repository_id"),
            )
            check(step.source.commit_sha, "commit_sha", path + ("source", "commit_sha"))
            if step.source.profile_digest not in admitted:
                issues.add("profile_unsupported", path + ("source", "profile_digest"))
        if isinstance(step, (PolicyEvaluationStep, RegisteredGithubHandoffStep)):
            check(step.target_id, "identifier", path + ("target_id",))
            check(step.environment, "identifier", path + ("environment",))


class _Metadata(ClosedModel):
    project_id: Identifier
    workspace_id: Identifier | None
    environment: Identifier


class _SuppliedOutput(ClosedModel):
    step_id: Identifier
    output: OutputKind
    handle: Identifier


@dataclass(frozen=True)
class OutputHandle:
    step_id: str
    output: str
    handle: str


@dataclass(frozen=True)
class ResolutionContext:
    inputs: tuple[tuple[str, str | int | bool], ...]
    metadata: tuple[tuple[str, str | None], ...]
    outputs: tuple[OutputHandle, ...]
    producers: tuple[tuple[str, str | None], ...]


class ResolutionError(ValueError):
    def __init__(self, code: str):
        issues = IssueCollector()
        issues.add(code)
        self.errors = issues.errors
        super().__init__(_MESSAGES[code])


def prepare_resolution(
    workflow: Workflow,
    supplied_inputs: dict[str, Any],
    metadata: dict[str, Any],
    supplied_outputs: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    *,
    registry_contract: RegistryContract | None = None,
) -> ResolutionContext:
    """Copy exact input values and opaque outputs; never execute or infer success."""
    try:
        if type(workflow) is not Workflow:
            raise ResolutionError("invalid_input")
        workflow = Workflow.model_validate(workflow.model_dump(warnings="error"))
        if registry_contract is None:
            registry_contract = RegistryContract()
        if type(registry_contract) is not RegistryContract:
            raise ResolutionError("invalid_input")
        registry_contract = RegistryContract.model_validate(
            registry_contract.model_dump(warnings="error")
        )
        issues = IssueCollector()
        _validate_scalar_references(workflow, registry_contract, issues)
        if not issues.has_errors:
            _validate_graph(workflow, registry_contract, issues)
        if issues.has_errors:
            raise ResolutionError(issues.errors[0].code)
        if (
            type(supplied_inputs) is not dict
            or len(supplied_inputs) > 32
            or any(
                type(key) is not str or key not in workflow.inputs
                for key in supplied_inputs
            )
        ):
            raise ResolutionError("input_value_invalid")
        values: dict[str, str | int | bool] = {}
        for name, declaration in workflow.inputs.items():
            value = supplied_inputs.get(name, declaration.default)
            valid = False
            if (
                declaration.type in ("identifier", "commit_sha", "string")
                and type(value) is str
                and len(value) <= 1024
                and not any(0xD800 <= ord(char) <= 0xDFFF for char in value)
            ):
                if declaration.type == "identifier":
                    valid = (
                        len(value) <= 128
                        and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]*", value)
                        is not None
                    )
                elif declaration.type == "commit_sha":
                    valid = (
                        len(value) == 40
                        and re.fullmatch(r"[0-9a-f]{40}", value) is not None
                    )
                elif isinstance(declaration, StringInput):
                    valid = len(value) <= declaration.max_length
            elif declaration.type == "integer":
                valid = (
                    type(value) is int
                    and declaration.minimum <= value <= declaration.maximum
                )
            elif declaration.type == "boolean":
                valid = type(value) is bool
            if not valid:
                raise ResolutionError("input_value_invalid")
            values[name] = cast(str | int | bool, value)
        if (
            type(metadata) is not dict
            or len(metadata) != 3
            or any(type(key) is not str for key in metadata)
        ):
            raise ResolutionError("metadata_mismatch")
        if any(
            type(value) is not str and not (key == "workspace_id" and value is None)
            for key, value in metadata.items()
        ):
            raise ResolutionError("metadata_mismatch")
        if (
            isinstance(workflow.environment, InputReference)
            and workflow.inputs.get(workflow.environment.name, None) is not None
            and workflow.inputs[workflow.environment.name].type != "identifier"
        ):
            raise ResolutionError("reference_type")
        try:
            meta = _Metadata.model_validate(metadata)
        except ValidationError:
            raise ResolutionError("metadata_mismatch") from None
        environment = (
            values.get(workflow.environment.name)
            if type(workflow.environment) is InputReference
            else workflow.environment
        )
        if (
            meta.project_id != workflow.project_id
            or meta.environment != environment
            or (
                workflow.workspace_id is not None
                and workflow.workspace_id != meta.workspace_id
            )
        ):
            raise ResolutionError("metadata_mismatch")
        if type(supplied_outputs) not in (list, tuple) or len(supplied_outputs) > 50:
            raise ResolutionError("output_invalid")
        producers = {
            step.id: STEP_CONTRACTS[step.kind].output for step in workflow.steps
        }
        if len(producers) != len(workflow.steps):
            raise ResolutionError("output_invalid")
        outputs: list[OutputHandle] = []
        seen: set[tuple[str, str]] = set()
        for record in supplied_outputs:
            if (
                type(record) is not dict
                or len(record) != 3
                or any(
                    type(key) is not str or type(value) is not str
                    for key, value in record.items()
                )
            ):
                raise ResolutionError("output_invalid")
            try:
                output = _SuppliedOutput.model_validate(record)
            except ValidationError:
                raise ResolutionError("output_invalid") from None
            output_key = (output.step_id, output.output)
            if output_key in seen or producers.get(output.step_id) != output.output:
                raise ResolutionError("output_invalid")
            seen.add(output_key)
            outputs.append(OutputHandle(output.step_id, output.output, output.handle))
        return ResolutionContext(
            tuple(values.items()),
            tuple(meta.model_dump().items()),
            tuple(outputs),
            tuple(producers.items()),
        )
    except ResolutionError:
        raise
    except Exception:
        raise ResolutionError("invalid_input") from None


def resolve_value(
    value: Any, context: ResolutionContext
) -> str | int | bool | None | OutputHandle:
    """Resolve a whole value using supplied immutable data, without evaluation."""
    if type(context) is not ResolutionContext:
        raise ResolutionError("invalid_input")
    _check_resolution_context(context)
    if type(value) in (InputReference, ProjectReference, RunReference, StepReference):
        try:
            value = type(value).model_validate(value.model_dump(warnings="error"))
        except Exception:
            raise ResolutionError("reference_invalid") from None
    if type(value) in (str, int, bool):
        if type(value) is int and abs(value) > SAFE_INTEGER:
            raise ResolutionError("input_value_invalid")
        if type(value) is str and (
            len(value) > 1024 or any(0xD800 <= ord(char) <= 0xDFFF for char in value)
        ):
            raise ResolutionError("input_value_invalid")
        return value
    if type(value) is InputReference:
        for name, supplied in context.inputs:
            if name == value.name:
                return supplied
        raise ResolutionError("reference_invalid")
    if type(value) in (ProjectReference, RunReference):
        field = (
            "project_id"
            if type(value) is ProjectReference and value.field == "id"
            else value.field
        )
        for key, metadata_value in context.metadata:
            if key == field:
                return metadata_value
        raise ResolutionError("reference_invalid")
    if type(value) is StepReference:
        for output in context.outputs:
            if (output.step_id, output.output) == (value.step_id, value.output):
                return output
        raise ResolutionError("output_invalid")
    raise ResolutionError("reference_invalid")


def _check_resolution_context(context: ResolutionContext) -> None:
    # Dataclass constructors (like Pydantic model_construct) are not authority.
    if (
        any(
            type(value) is not tuple
            for value in (
                context.inputs,
                context.metadata,
                context.outputs,
                context.producers,
            )
        )
        or len(context.inputs) > 32
        or len(context.metadata) != 3
        or len(context.outputs) > 50
        or len(context.producers) > 50
    ):
        raise ResolutionError("invalid_input")
    try:
        input_names = set()
        for pair in context.inputs:
            if type(pair) is not tuple or len(pair) != 2:
                raise ValueError
            name, scalar = pair
            if (
                type(name) is not str
                or not 1 <= len(name) <= 128
                or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]*", name) is None
                or name in input_names
            ):
                raise ValueError
            input_names.add(name)
            if (
                type(scalar) not in (str, int, bool)
                or (type(scalar) is int and abs(scalar) > SAFE_INTEGER)
                or (
                    type(scalar) is str
                    and (
                        len(scalar) > 1024
                        or any(0xD800 <= ord(char) <= 0xDFFF for char in scalar)
                    )
                )
            ):
                raise ValueError
        if any(type(pair) is not tuple or len(pair) != 2 for pair in context.metadata):
            raise ValueError
        if any(
            type(key) is not str
            or (
                type(value) is not str and not (key == "workspace_id" and value is None)
            )
            for key, value in context.metadata
        ):
            raise ValueError
        _Metadata.model_validate(dict(context.metadata))
        if any(
            type(pair) is not tuple
            or len(pair) != 2
            or type(pair[0]) is not str
            or (pair[1] is not None and type(pair[1]) is not str)
            for pair in context.producers
        ):
            raise ValueError
        producers = dict(context.producers)
        if len(producers) != len(context.producers):
            raise ValueError
        for key, producer_output in producers.items():
            if (
                type(key) is not str
                or not 1 <= len(key) <= 128
                or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.:-]*", key) is None
                or producer_output
                not in (
                    None,
                    "screened_artifacts",
                    "report",
                    "action_binding",
                    "decision_receipt",
                )
            ):
                raise ValueError
        seen: set[tuple[str, str]] = set()
        for output in context.outputs:
            if type(output) is not OutputHandle:
                raise ValueError
            if any(
                type(value) is not str
                for value in (output.step_id, output.output, output.handle)
            ):
                raise ValueError
            _SuppliedOutput.model_validate(
                {
                    "step_id": output.step_id,
                    "output": output.output,
                    "handle": output.handle,
                }
            )
            output_key = (output.step_id, output.output)
            if output_key in seen or producers.get(output.step_id) != output.output:
                raise ValueError
            seen.add(output_key)
    except Exception:
        raise ResolutionError("invalid_input") from None


@dataclass(frozen=True)
class WorkflowValidationResult:
    """Immutable canonical result with a fresh typed view on each access."""

    canonical_bytes: bytes | None = None
    digest: str | None = None
    topological_order: tuple[str, ...] = ()
    errors: tuple[Diagnostic, ...] = ()
    truncated: bool = False
    canonicalization: str = "tuple-json-utf8-v1"

    @property
    def valid(self) -> bool:
        return self.canonical_bytes is not None and not self.errors

    @property
    def definition(self) -> Workflow | None:
        # Never expose mutable lists/maps that can drift from the stored digest.
        if self.canonical_bytes is None:
            return None
        return Workflow.model_validate_json(self.canonical_bytes)


def _graph_order(
    workflow: Workflow, issues: IssueCollector
) -> tuple[dict[str, Step], dict[str, set[str]], tuple[str, ...]]:
    nodes: dict[str, Step] = {}
    positions: dict[str, int] = {}
    for index, step in enumerate(workflow.steps):
        if step.id in nodes:
            issues.add("dependency_invalid", ("steps", index, "id"))
        nodes[step.id] = step
        positions[step.id] = index
    for index, step in enumerate(workflow.steps):
        seen: set[str] = set()
        for offset, parent in enumerate(step.depends_on):
            if parent not in nodes or parent == step.id or parent in seen:
                issues.add("dependency_invalid", ("steps", index, "depends_on", offset))
            seen.add(parent)
    if issues.has_errors:
        return nodes, {}, ()
    indegree = {name: len(step.depends_on) for name, step in nodes.items()}
    children: dict[str, list[str]] = {name: [] for name in nodes}
    for name, step in nodes.items():
        for parent in step.depends_on:
            children[parent].append(name)
    ready = [name for name in nodes if indegree[name] == 0]
    heapq.heapify(ready)
    order: list[str] = []
    ancestors: dict[str, set[str]] = {}
    while ready:
        name = heapq.heappop(ready)
        order.append(name)
        parents = set(nodes[name].depends_on)
        for parent in nodes[name].depends_on:
            parents.update(ancestors[parent])
        ancestors[name] = parents
        for child in children[name]:
            indegree[child] -= 1
            if not indegree[child]:
                heapq.heappush(ready, child)
    if len(order) != len(nodes):
        # Locate one actual back edge rather than blaming a downstream blocked node.
        visiting: set[str] = set()
        visited: set[str] = set()

        def cycle(name: str) -> bool:
            visiting.add(name)
            for offset, parent in enumerate(nodes[name].depends_on):
                if parent in visiting:
                    issues.add(
                        "graph_cycle", ("steps", positions[name], "depends_on", offset)
                    )
                    return True
                if parent not in visited and cycle(parent):
                    return True
            visiting.remove(name)
            visited.add(name)
            return False

        for name in sorted(nodes):
            if name not in visited and cycle(name):
                break
        return nodes, {}, ()
    return nodes, ancestors, tuple(order)


def _validate_graph(
    workflow: Workflow, registry: RegistryContract, issues: IssueCollector
) -> tuple[str, ...]:
    nodes, ancestors, order = _graph_order(workflow, issues)
    if issues.has_errors:
        return ()
    for index, step in enumerate(workflow.steps):
        for field, expected in STEP_CONTRACTS[step.kind].inputs:
            reference = cast(StepReference, getattr(step, field))
            producer = nodes.get(reference.step_id)
            path = ("steps", index, field)
            if producer is None or reference.step_id not in ancestors[step.id]:
                issues.add("reference_invalid", path + ("step_id",))
            elif (
                reference.output != expected
                or STEP_CONTRACTS[producer.kind].output != expected
            ):
                issues.add("reference_type", path + ("output",))
    # No cross-node traversal until every local reference and type has qualified.
    if issues.has_errors:
        return ()
    profiles = {profile.digest: profile for profile in registry.profiles}
    root_environment = normalize_identifier(workflow.environment, workflow)
    for index, step in enumerate(workflow.steps):
        if isinstance(step, (PolicyEvaluationStep, RegisteredGithubHandoffStep)):
            if normalize_identifier(step.environment, workflow) != root_environment:
                issues.add("binding_mismatch", ("steps", index, "environment"))
        if type(step) is PolicyEvaluationStep:
            analysis = cast(SharedAnalysisStep, nodes[step.report.step_id])
            source = nodes[analysis.artifact.step_id]
            if type(source) is UploadedIntakeStep:
                if step.authorization_kind != "advisory_request":
                    issues.add(
                        "scope_unsupported", ("steps", index, "authorization_kind")
                    )
            elif type(source) is AdmittedCollectionStep:
                profile = profiles.get(source.source.profile_digest)
                if (
                    profile is None
                    or step.authorization_kind not in profile.authorization_kinds
                ):
                    issues.add(
                        "profile_unsupported", ("steps", index, "authorization_kind")
                    )
        elif type(step) is RegisteredGithubHandoffStep:
            gate = cast(PolicyEvaluationStep, nodes[step.binding.step_id])
            decision = cast(HumanDecisionStep, nodes[step.decision.step_id])
            if decision.binding != step.binding:
                issues.add("binding_mismatch", ("steps", index, "decision"))
            if normalize_identifier(gate.target_id, workflow) != normalize_identifier(
                step.target_id, workflow
            ):
                issues.add("binding_mismatch", ("steps", index, "target_id"))
            if normalize_identifier(gate.environment, workflow) != normalize_identifier(
                step.environment, workflow
            ):
                issues.add("binding_mismatch", ("steps", index, "environment"))
            if gate.authorization_kind != step.authorization_kind:
                issues.add("binding_mismatch", ("steps", index, "authorization_kind"))
    return order


def validate_workflow(
    definition_bytes: bytes,
    limits: ValidationLimits | None = None,
    registry_contract: RegistryContract | None = None,
) -> WorkflowValidationResult:
    """Validate the complete closed contract without I/O, handlers or evaluation.

    Defaults are hard contract ceilings and an empty admitted-profile catalog.
    Applications supply configuration limits and trusted registry data explicitly.
    """
    issues = IssueCollector()
    try:
        if limits is None:
            limits = ValidationLimits()
        if registry_contract is None:
            registry_contract = RegistryContract()
        if (
            type(limits) is not ValidationLimits
            or type(registry_contract) is not RegistryContract
        ):
            issues.add("invalid_input")
        else:
            limits = ValidationLimits.model_validate(
                limits.model_dump(warnings="error")
            )
            registry_contract = RegistryContract.model_validate(
                registry_contract.model_dump(warnings="error")
            )
            issues = IssueCollector(limits.max_errors)
            workflow = _parse_definition(definition_bytes, limits, issues)
            if workflow is not None and not issues.has_errors:
                _validate_scalar_references(workflow, registry_contract, issues)
                order = (
                    ()
                    if issues.has_errors
                    else _validate_graph(workflow, registry_contract, issues)
                )
                if not issues.has_errors:
                    canonical = json.dumps(
                        workflow.model_dump(mode="json"),
                        sort_keys=True,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        allow_nan=False,
                    ).encode("utf-8")
                    if len(canonical) > limits.max_bytes:
                        issues.add("resource_limit")
                    else:
                        return WorkflowValidationResult(
                            canonical_bytes=canonical,
                            digest="sha256:" + hashlib.sha256(canonical).hexdigest(),
                            topological_order=order,
                        )
    except Exception:
        issues.add("invalid_input")
    return WorkflowValidationResult(errors=issues.errors, truncated=issues.truncated)
