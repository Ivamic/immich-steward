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
		case 'immich_invalid_credentials':
			return m.error_immich_invalid_credentials();
		case 'immich_password_login_failed':
			return m.error_immich_password_login_failed();
		case 'map_source_needs_key':
			return m.error_map_source_needs_key();
		case 'map_source_not_enabled':
			return m.error_map_source_not_enabled();
		case 'immich_error':
			return m.error_immich_error();
		case 'location_null_island':
			return m.error_location_null_island();
		case 'location_clear_failed':
			return m.error_location_clear_failed();
		case 'location_changed_in_immich':
			return m.error_location_changed_in_immich();
		case 'location_nothing_to_undo':
			return m.error_location_nothing_to_undo();
		case 'rotate_not_supported':
			return m.error_rotate_not_supported();
		default:
			return m.error_unexpected();
	}
}
