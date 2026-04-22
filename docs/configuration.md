# Configuration

SwitchBoard's supported runtime configuration is lane/backend-oriented:

- `config/policy.yaml`: ordered lane-selection rules
- `config/capabilities.yaml`: capability metadata
- `.env`: host/port, log level, file paths

`config/profiles.yaml` remains compatibility-only for legacy selector material and
is not required for the supported `/route` runtime.

There is no upstream provider configuration in the default runtime.
