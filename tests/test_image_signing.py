from urllib.parse import urlsplit

import pytest

from stech_mcp.services.image_signing import ImageUrlSigner, InvalidImageToken


def _token(url: str) -> str:
    return urlsplit(url).path.rsplit("/", 1)[-1]


def test_signed_image_url_round_trips_exact_image_identity():
    signer = ImageUrlSigner(
        secret="secret-value-for-tests",
        public_base="https://mcp.artos.pe/vtex-images",
        ttl_seconds=900,
        now=lambda: 1_000,
    )

    url = signer.sign(product_image_id=17, partnumber="82YU00XYLM")
    payload = signer.verify(_token(url))

    assert url.startswith("https://mcp.artos.pe/vtex-images/")
    assert payload == {
        "product_image_id": 17,
        "partnumber": "82YU00XYLM",
        "expires_at": 1900,
    }


def test_tampered_image_token_is_rejected():
    signer = ImageUrlSigner(
        secret="secret-value-for-tests",
        public_base="https://mcp.artos.pe/vtex-images",
        ttl_seconds=900,
        now=lambda: 1_000,
    )
    token = _token(signer.sign(product_image_id=17, partnumber="82YU00XYLM"))
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")

    with pytest.raises(InvalidImageToken, match="signature"):
        signer.verify(tampered)


def test_expired_image_token_is_rejected():
    clock = {"now": 1_000}
    signer = ImageUrlSigner(
        secret="secret-value-for-tests",
        public_base="https://mcp.artos.pe/vtex-images",
        ttl_seconds=5,
        now=lambda: clock["now"],
    )
    token = _token(signer.sign(product_image_id=17, partnumber="82YU00XYLM"))
    clock["now"] = 1_006

    with pytest.raises(InvalidImageToken, match="expired"):
        signer.verify(token)
