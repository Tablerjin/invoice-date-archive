from safe_output import replace_output


def test_output_does_not_follow_symlink(tmp_path):
    outside = tmp_path / 'outside'
    outside.write_text('original')
    archive = tmp_path / 'archive'
    archive.mkdir()
    output = archive / 'report.html'
    output.symlink_to(outside)
    replace_output(output, lambda p: p.write_text('report'))
    assert outside.read_text() == 'original'
    assert not output.is_symlink()
    assert output.read_text() == 'report'
