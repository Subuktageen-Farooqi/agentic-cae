import base64

import pytest

from schemas import DesignBrief, Intake
from storage import Store, Upload


@pytest.fixture
def png_bytes():
    # An actual 1x1 PNG fixture; no vision interpretation is asserted by these tests.
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jS1sAAAAASUVORK5CYII="
    )


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data")


@pytest.fixture
def project(store, png_bytes):
    return store.create_project(Intake(idea="A support arm", purpose="Carry a small device"),
                                [Upload("reference.png", "image/png", png_bytes)])


@pytest.fixture
def brief(store, project):
    value = DesignBrief(design_name="Support arm", description="A simple connected part",
                        reference_image_ids=store.original_intake(project).reference_image_ids,
                        assumptions=["Dimensions have not yet been chosen"])
    return store.save_brief(project, value, expected_version=0, actor="user", reason="Initial brief")
