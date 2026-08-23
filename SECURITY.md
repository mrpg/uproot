# Security

## Signatures

Cryptographic signatures can be verified using _(1)_ the following OpenPGP key:

    A09A92FC5015EE861A7098511999861C1636BA9B

The public key is available [in this repository](./1636BA9B.asc) and from [here](https://max.pm/1636BA9B.asc). Consider reviewing Max Grossmann’s [security page](https://max.pm/security/) and [security repository](https://github.com/mrpg/security).

and _(2)_ the following SLH-DSA public key:

```
-----BEGIN PUBLIC KEY-----
MFAwCwYJYIZIAWUDBAMeA0EAks5RsTEMylbCeYJRzeQPqmW1TT+p36zmngbr5PMH
RzqAOp5v9cKZcrWaipZmJ7INuggKhboBdKKaXKOe7aydOg==
-----END PUBLIC KEY-----
```

Verify with GnuPG or [botan-slhdsa-signing](https://github.com/mrpg/botan-slhdsa-signing), respectively.

## Security vulnerabilities

If you believe you have found a security vulnerability in *uproot*, please report it privately rather than opening a public issue.

Please contact Max Grossmann using one of the methods listed [here](https://max.pm/contact/).

You can expect an initial response within a few days. Please include enough detail to reproduce the issue (affected version or commit, steps, and impact).

For sensitive reports, please encrypt to the following OpenPGP key:

    A09A92FC5015EE861A7098511999861C1636BA9B

If you don’t have a local OpenPGP setup, an in-browser tool to encrypt messages to this key is available [here](https://max.pm/contact/#encrypt).

The public key is available [in this repository](./1636BA9B.asc) and from [here](https://max.pm/1636BA9B.asc). Consider reviewing Max Grossmann’s [security page](https://max.pm/security/) and [security repository](https://github.com/mrpg/security).
