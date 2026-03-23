<!-- /!\ Non OCA Context : Set here the badge of your runbot / runboat instance. -->
[![Pre-commit Status](https://github.com/it-projects-llc/glitchtip-alert-telegram-bot/actions/workflows/pre-commit.yml/badge.svg?branch=18.0)](https://github.com/it-projects-llc/glitchtip-alert-telegram-bot/actions/workflows/pre-commit.yml?query=branch%3A18.0)
[![Build Status](https://github.com/it-projects-llc/glitchtip-alert-telegram-bot/actions/workflows/test.yml/badge.svg?branch=18.0)](https://github.com/it-projects-llc/glitchtip-alert-telegram-bot/actions/workflows/test.yml?query=branch%3A18.0)
[![codecov](https://codecov.io/gh/it-projects-llc/glitchtip-alert-telegram-bot/branch/18.0/graph/badge.svg)](https://codecov.io/gh/it-projects-llc/glitchtip-alert-telegram-bot)
<!-- /!\ Non OCA Context : Set here the badge of your translation instance. -->

<!-- /!\ do not modify above this line -->

#



<!-- /!\ do not modify below this line -->

<!-- prettier-ignore-start -->

[//]: # (addons)

This part will be replaced when running the oca-gen-addons-table script from OCA/maintainer-tools.

[//]: # (end addons)

<!-- prettier-ignore-end -->

## Licenses

This repository is licensed under [AGPL-3.0](LICENSE).

However, each module can have a totally different license, as long as they adhere to IT-Projects LLC
policy. Consult each module's `__manifest__.py` file, which contains a `license` key
that explains its license.

----

## Project-based Telegram mentions

Use `PROJECT_TELEGRAM_MENTIONS` to map one project to many Telegram users and one user to many projects.

Format:

`project_name:mention1,mention2;another_project:mention3`

Supported mention targets:

- `@username`
- `id:123456789` (Telegram numeric user ID)
- `123456789` (same as above)

Example:

`PROJECT_TELEGRAM_MENTIONS=shop-api:@alice,@bob;billing:id:123456789,@oncall_ops`

Mentions are injected into alert messages only for service state changes (`UP`/`DOWN`) to reduce notification noise.

Mention lookup order:

1. exact match against the `Project` field
2. fallback to title matching (useful for uptime monitor alerts that only provide service name in `Title`)
