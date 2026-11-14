"""Fails when a direct dependency is deprecated, archived, inactive or yanked.

Checks the locked versions of every direct dependency (including dev groups) against the PyPI
and npm registries. Usage: `check_deprecated_deps.py [project ...]` (all projects by default).
"""

import json
import re
import sys
import tomllib
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON_PROJECTS = ("backend", "eval")
NODE_PROJECTS = ("frontend",)
TIMEOUT_S = 20
INACTIVE_CLASSIFIER = "Development Status :: 7 - Inactive"
REQUIREMENT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")


@dataclass(frozen=True)
class Dependency:
    ecosystem: str
    project: str
    name: str
    version: str


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def fetch_json(url: str, accept: str = "application/json") -> dict[str, object]:
    request = urllib.request.Request(url, headers={"Accept": accept})  # noqa: S310
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:  # noqa: S310
        payload: object = json.load(response)
    if not isinstance(payload, dict):
        message = f"Unexpected response from {url}"
        raise TypeError(message)
    return {str(key): value for key, value in payload.items()}


def as_dict(value: object) -> dict[str, object]:
    return {str(k): v for k, v in value.items()} if isinstance(value, dict) else {}


def python_dependencies(project: str) -> list[Dependency]:
    pyproject = tomllib.loads((ROOT / project / "pyproject.toml").read_text(encoding="utf-8"))
    lock = tomllib.loads((ROOT / project / "uv.lock").read_text(encoding="utf-8"))
    requirements: list[str] = list(pyproject.get("project", {}).get("dependencies", []))
    for group in pyproject.get("dependency-groups", {}).values():
        requirements.extend(item for item in group if isinstance(item, str))
    locked = {normalize(pkg["name"]): str(pkg["version"]) for pkg in lock.get("package", [])}
    dependencies = []
    for requirement in requirements:
        match = REQUIREMENT_NAME.match(requirement)
        if match is None:
            continue
        name = normalize(match.group(0))
        if name in locked:
            dependencies.append(Dependency("pypi", project, name, locked[name]))
    return dependencies


def node_dependencies(project: str) -> list[Dependency]:
    manifest = as_dict(json.loads((ROOT / project / "package.json").read_text(encoding="utf-8")))
    lock = as_dict(json.loads((ROOT / project / "package-lock.json").read_text(encoding="utf-8")))
    packages = as_dict(lock.get("packages"))
    names = [*as_dict(manifest.get("dependencies")), *as_dict(manifest.get("devDependencies"))]
    dependencies = []
    for name in names:
        version = as_dict(packages.get(f"node_modules/{name}")).get("version")
        if isinstance(version, str):
            dependencies.append(Dependency("npm", project, name, version))
    return dependencies


def pypi_problems(dep: Dependency) -> list[str]:
    problems = []
    simple = fetch_json(
        f"https://pypi.org/simple/{dep.name}/", accept="application/vnd.pypi.simple.v1+json"
    )
    status = as_dict(simple.get("project-status")).get("status")
    if isinstance(status, str) and status != "active":
        problems.append(f"project status is '{status}'")
    info = as_dict(fetch_json(f"https://pypi.org/pypi/{dep.name}/{dep.version}/json").get("info"))
    if info.get("yanked") is True:
        problems.append(f"version is yanked ({info.get('yanked_reason') or 'no reason given'})")
    classifiers = info.get("classifiers")
    if isinstance(classifiers, list) and INACTIVE_CLASSIFIER in classifiers:
        problems.append("project is marked inactive")
    return problems


def npm_problems(dep: Dependency) -> list[str]:
    name = urllib.parse.quote(dep.name, safe="@")
    deprecated = fetch_json(f"https://registry.npmjs.org/{name}/{dep.version}").get("deprecated")
    return [f"deprecated: {deprecated}"] if isinstance(deprecated, str) and deprecated else []


def check(dep: Dependency) -> list[str]:
    try:
        problems = pypi_problems(dep) if dep.ecosystem == "pypi" else npm_problems(dep)
    except (OSError, TypeError, ValueError) as error:
        problems = [f"could not be checked: {error}"]
    return [f"[{dep.project}] {dep.name}=={dep.version}: {problem}" for problem in problems]


def main(selected: list[str]) -> int:
    unknown = set(selected) - {*PYTHON_PROJECTS, *NODE_PROJECTS}
    if unknown:
        sys.stderr.write(f"Unknown projects: {', '.join(sorted(unknown))}\n")
        return 2
    wanted = set(selected) or {*PYTHON_PROJECTS, *NODE_PROJECTS}
    dependencies = [
        dep
        for project in PYTHON_PROJECTS
        if project in wanted
        for dep in python_dependencies(project)
    ]
    dependencies += [
        dep for project in NODE_PROJECTS if project in wanted for dep in node_dependencies(project)
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        problems = [problem for result in pool.map(check, dependencies) for problem in result]
    for problem in problems:
        sys.stderr.write(f"{problem}\n")
    sys.stdout.write(f"Checked {len(dependencies)} direct dependencies: {len(problems)} problems\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
