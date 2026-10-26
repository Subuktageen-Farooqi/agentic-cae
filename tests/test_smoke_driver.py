"""Smoke-driver negative gates with no live transport or generated-code execution."""
import subprocess
import sys
import pytest
from examples.container_check import assert_rectangular_metrics
from examples.live_smoke import preflight, sketch
from config import Config
from schemas import BoundingBox, GeometryMetrics


def test_live_driver_requires_explicit_opt_in():
    process=subprocess.run([sys.executable,"-m","examples.live_smoke","prepare"],capture_output=True,text=True)
    assert process.returncode==2 and "--live is required" in process.stderr


def test_missing_config_blocks_before_any_sdk_construction():
    with pytest.raises(RuntimeError,match="no live request sent"):
        preflight(Config.from_env({}),"does-not-exist.json")


def test_reference_is_actual_readable_sketch():
    from PIL import Image
    import io
    image=Image.open(io.BytesIO(sketch()))
    assert image.format=="PNG" and image.size==(640,240)
    assert len(image.getcolors()) > 1


def test_cantilever_comparison_rejects_wrong_volume_or_dimensions():
    metrics=GeometryMetrics(revision_id="unit",geometry_hash="a"*64,step_import_succeeded=True,
        shape_nonempty=True,shape_valid=True,solid_count=1,volume_mm3=20000,
        bounding_box=BoundingBox(minimum=(0,-10,-5),maximum=(100,10,5)),evidence_path="unit")
    assert_rectangular_metrics(metrics)
    with pytest.raises(ValueError): assert_rectangular_metrics(metrics.model_copy(update={"volume_mm3":19000}))
