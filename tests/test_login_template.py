import pytest

from uproot import server2


@pytest.mark.asyncio
async def test_login_token_page_hides_manual_login_form():
    html = await server2.render(
        "Login.html",
        {
            "bad": False,
            "login_token_enabled": True,
            "pow_challenge": "challenge",
            "pow_difficulty": "0000",
        },
    )

    assert "<i>Here be dragons.</i>" in html
    assert 'id="uproot-form"' in html
    assert 'id="token"' in html
    assert 'type="hidden" id="user"' in html
    assert 'type="hidden" id="pw"' in html
    assert 'type="text"' not in html
    assert 'type="password"' not in html
    assert 'type="submit"' not in html


@pytest.mark.asyncio
async def test_password_login_page_keeps_manual_login_form():
    html = await server2.render(
        "Login.html",
        {
            "bad": False,
            "login_token_enabled": False,
            "pow_challenge": "challenge",
            "pow_difficulty": "0000",
        },
    )

    assert "<i>Here be dragons.</i>" not in html
    assert 'id="user"' in html
    assert 'id="pw"' in html
    assert 'type="submit"' in html
