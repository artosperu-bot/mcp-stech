from pathlib import Path


def test_falabella_excel_script_uses_fixed_channel_folders():
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts" / "falabella_fill_excel_images.py").read_text(encoding="utf-8")

    assert 'PROJECT_ROOT / "EXCEL" / "FALABELLA" / "ENTRADA"' in source
    assert 'PROJECT_ROOT / "EXCEL" / "FALABELLA" / "SALIDA"' in source
    assert 'nargs="?"' in source
    assert "_latest_input()" in source


def test_falabella_one_command_runners_exist():
    root = Path(__file__).resolve().parents[1]

    powershell = root / "RUN_FALABELLA_EXCEL.ps1"
    batch = root / "FALABELLA_EXCEL.bat"

    assert powershell.exists()
    assert batch.exists()
    assert "EXCEL\\FALABELLA\\ENTRADA" in powershell.read_text(encoding="utf-8")
    assert "EXCEL\\FALABELLA\\SALIDA" in powershell.read_text(encoding="utf-8")
