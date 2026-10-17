// SPDX-License-Identifier: AGPL-3.0-or-later
// Turns API error codes into messages in the current language.
import { ApiError } from '#lib/api.js';
import { m } from '#lib/paraglide/messages.js';

export function errorMessage(error: unknown): string {
	if (!(error instanceof ApiError)) return m.error_unexpected();
	const p = error.params;
	switch (error.code) {
		case 'core_unreachable':
			return m.error_core_unreachable();
		case 'server_not_configured':
			return m.error_server_not_configured();
		case 'not_authenticated':
			return m.error_not_authenticated();
		case 'immich_unreachable':
			return m.error_immich_unreachable();
		case 'immich_invalid_api_key':
			return m.error_immich_invalid_api_key();
		case 'immich_missing_permissions': {
			const list = Array.isArray(p.permissions) ? p.permissions.join(', ') : '';
			return list
				? m.error_immich_missing_permissions({ permissions: list })
				: m.error_immich_permission_denied();
		}
		case 'immich_unsupported_version':
			return m.error_immich_unsupported_version({ version: String(p.version ?? '?') });
		default:
			return m.error_unexpected();
	}
}
