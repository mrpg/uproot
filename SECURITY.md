# Security

## Signatures

Starting with uproot 0.13.0, release artifacts have detached signatures in the following formats.

See the `security` submodule and Max Grossmann’s [security page](https://max.pm/security/) for more information.

### `*.asc`

Verify these OpenPGP signatures with GnuPG using the key with this fingerprint.

    A09A92FC5015EE861A7098511999861C1636BA9B

Download the [OpenPGP public key](https://max.pm/1636BA9B.asc).

### `*.botansigh`

Verify these SLH-DSA signatures with [botan-slhdsa-signing](https://github.com/mrpg/botan-slhdsa-signing) using the public key below.

```
-----BEGIN PUBLIC KEY-----
MFAwCwYJYIZIAWUDBAMeA0EAks5RsTEMylbCeYJRzeQPqmW1TT+p36zmngbr5PMH
RzqAOp5v9cKZcrWaipZmJ7INuggKhboBdKKaXKOe7aydOg==
-----END PUBLIC KEY-----
```

### `*.sig`

These signatures use the experimental OpenPGP v6 key with this primary-key fingerprint.

    C1E8235A94BE2427043C08EEF79F9481E44A587ACC5B0D2631BE34C3A8B949BC

Download the [public key](https://max.pm/C1E8235A94BE2427.asc) and verify with an OpenPGP implementation that supports its post-quantum hybrid algorithm.

## Security vulnerabilities

If you believe you have found a security vulnerability in *uproot*, please report it privately rather than opening a public issue.

Please contact Max Grossmann using one of the methods listed [here](https://max.pm/contact/).

You can expect an initial response within a few days. Please include enough detail to reproduce the issue (affected version or commit, steps, and impact).

For sensitive reports, please encrypt to the following OpenPGP key:

    A09A92FC5015EE861A7098511999861C1636BA9B

If you don’t have a local OpenPGP setup, an in-browser tool to encrypt messages to this key is available [here](https://max.pm/contact/#encrypt).

The public key is available from [here](https://max.pm/1636BA9B.asc). Consider reviewing Max Grossmann’s [security page](https://max.pm/security/). The `security` submodule in here contains further information.
