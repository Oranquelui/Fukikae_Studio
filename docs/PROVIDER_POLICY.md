# Provider Policy

FukiKae Studio has exactly one approved AI provider boundary for the MVP: xAI.

Allowed provider value:

- `xai`

Forbidden provider values include, but are not limited to:

- Soniox
- Supertone
- Supertonic
- OpenAI
- ElevenLabs
- Anthropic
- Google
- Azure
- Any other non-xAI AI provider

Runtime code must validate provider configuration before any AI client is initialized. Error messages must be safe: they should explain the xAI-only policy without echoing secrets or raw configuration values.

Default tests must use fixtures or mocks only. Live xAI calls are forbidden in the current implementation phase.

## Solo local beta mode

The solo beta path is fixture-backed and local-only:

- No live xAI/Grok API call is required.
- No API key is required.
- Local media is not uploaded.
- `fukikae studio` binds to loopback by default.
- Validation artifacts must not contain secrets.

## Future live mode credential policy

Future live xAI/Grok mode should use BYOK (bring your own key):

- The user enters their own xAI/Grok API key.
- The key is stored only on the user's local machine.
- Preferred storage is OS secret storage, such as macOS Keychain.
- If OS secret storage is unavailable, use encrypted local storage with a clear user-controlled boundary.
- The key must not be stored in a hosted backend, shared cloud database, analytics event, validation report, project artifact, or log file.
- Error messages must redact authorization headers, API keys, request metadata, and raw provider configuration values.
