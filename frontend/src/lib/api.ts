// SPDX-License-Identifier: AGPL-3.0-or-later
// Typed client for the core API. Mirrors the Pydantic models in core/src/steward/api.

export interface DatabaseHealth {
	ok: boolean;
	server_version: string | null;
	pgvector_version: string | null;
	/** Machine-readable error code; translated by the UI. */
	error: string | null;
}

export interface Health {
	status: 'ok' | 'degraded';
	version: string;
	database: DatabaseHealth;
}

export async function getHealth(fetchFn: typeof fetch = fetch): Promise<Health> {
	const response = await fetchFn('/api/health');
	if (!response.ok) {
		throw new Error(`GET /api/health failed: ${response.status}`);
	}
	return (await response.json()) as Health;
}
