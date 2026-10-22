// SPDX-License-Identifier: AGPL-3.0-or-later
// Typed client for the core API. Mirrors the Pydantic models in core/src/steward/api.

/** Error returned by the core: a machine-readable code plus parameters for the message. */
export class ApiError extends Error {
	constructor(
		readonly status: number,
		readonly code: string,
		readonly params: Record<string, unknown> = {}
	) {
		super(code);
	}
}

async function request<T>(
	method: string,
	path: string,
	body?: unknown,
	// Lets the request outlive the page (used when the tab is closed during a pending save).
	keepalive = false
): Promise<T> {
	let response: Response;
	try {
		response = await fetch(path, {
			method,
			headers: body === undefined ? {} : { 'content-type': 'application/json' },
			body: body === undefined ? undefined : JSON.stringify(body),
			keepalive
		});
	} catch {
		throw new ApiError(0, 'core_unreachable');
	}
	if (response.status === 204) return undefined as T;
	const data = await response.json().catch(() => null);
	if (!response.ok) {
		throw new ApiError(response.status, data?.code ?? 'unexpected_error', data?.params ?? {});
	}
	return data as T;
}

export interface DatabaseHealth {
	ok: boolean;
	server_version: string | null;
	pgvector_version: string | null;
	/** Machine-readable error code; translated by the UI. */
	error: string | null;
}

export interface ImmichHealth {
	configured: boolean;
	reachable: boolean;
	version: string | null;
	supported: boolean | null;
}

export interface Health {
	status: 'ok' | 'degraded';
	version: string;
	database: DatabaseHealth;
	immich: ImmichHealth;
}

export interface Me {
	id: string;
	name: string;
	email: string;
}

export interface Job {
	id: string;
	kind: string;
	status: 'queued' | 'running' | 'done' | 'failed';
	progress: Record<string, unknown>;
	/** Error code, translated by the UI. */
	error: string | null;
	created_at: string;
	started_at: string | null;
	finished_at: string | null;
}

export interface Library {
	assets: number;
	videos: number;
	with_gps: number;
	without_gps: number;
	albums: number;
	synced_at: string | null;
	full_synced_at: string | null;
	sync_job: Job | null;
}

export const isActive = (job: Job | null) =>
	job !== null && (job.status === 'queued' || job.status === 'running');

/** Disjoint groups of photos; the gallery shows any combination of them. */
export type ShowCategory = 'todo' | 'with' | 'skipped' | 'not_applicable';
export const SHOW_CATEGORIES: readonly ShowCategory[] = [
	'todo',
	'with',
	'skipped',
	'not_applicable'
];
export type ReviewStatus = 'new' | 'skipped' | 'not_applicable';

export interface GalleryFilter {
	/** Groups to show; empty means all of them. */
	show: ShowCategory[];
	type: 'all' | 'image' | 'video';
	camera: string | null;
	album: string | null;
	date_from: string | null;
	date_to: string | null;
	archived: boolean;
	/** Only photos without a location that GeoCLIP places confidently. */
	geoclip_confident: boolean;
	/** Only photos whose latest run of this module failed... */
	failed_module: string | null;
	/** ...for this reason (a failure code); null: any reason. */
	failure: string | null;
}

export interface MonthBucket {
	month: string; // YYYY-MM
	count: number;
}

export interface AssetItem {
	id: string;
	local_taken_at: string;
	type: 'IMAGE' | 'VIDEO' | string;
	file_name: string;
	has_location: boolean;
	/** No location yet, but GeoCLIP places the photo confidently. */
	geoclip_confident: boolean;
	width: number | null;
	height: number | null;
	/** Changes with the thumbnails (photo rotated or edited in Immich). */
	version: string | null;
}

export interface FilterOptions {
	cameras: { value: string; make: string; model: string; count: number }[];
	albums: { id: string; name: string; count: number }[];
}

/** Query string for the gallery filter; default values are left out. */
export function filterQuery(filter: GalleryFilter, extra: Record<string, string> = {}): string {
	const params = new URLSearchParams(extra);
	for (const category of filter.show) params.append('show', category);
	if (filter.type !== 'all') params.set('type', filter.type);
	if (filter.camera !== null) params.set('camera', filter.camera);
	if (filter.album) params.set('album', filter.album);
	if (filter.date_from) params.set('date_from', filter.date_from);
	if (filter.date_to) params.set('date_to', filter.date_to);
	if (filter.archived) params.set('archived', 'true');
	if (filter.geoclip_confident) params.set('geoclip_confident', 'true');
	if (filter.failed_module) {
		params.set('failed_module', filter.failed_module);
		if (filter.failure) params.set('failure', filter.failure);
	}
	const query = params.toString();
	return query ? `?${query}` : '';
}

/** Clockwise, in degrees: how the user turned the photo in the app (Immich is not changed). */
export type Turn = 0 | 90 | 180 | 270;

/** The address changes with the thumbnails (`version`), so that the browser never keeps old ones. */
export const thumbnailUrl = (
	id: string,
	size: 'thumbnail' | 'preview' | 'fullsize' = 'thumbnail',
	turn: Turn = 0,
	version: string | null = null
) =>
	`/api/assets/${id}/thumbnail?size=${size}${turn ? `&turn=${turn}` : ''}` +
	(version ? `&v=${encodeURIComponent(version)}` : '');

export const getMonths = (filter: GalleryFilter) =>
	request<MonthBucket[]>('GET', `/api/assets/months${filterQuery(filter)}`);
export const getMonthAssets = (month: string, filter: GalleryFilter) =>
	request<AssetItem[]>('GET', `/api/assets${filterQuery(filter, { month })}`);
export const getFilterOptions = () => request<FilterOptions>('GET', '/api/assets/filter-options');

export interface LocationChange {
	id: string;
	created_at: string;
	latitude: number;
	longitude: number;
	prev_latitude: number | null;
	prev_longitude: number | null;
	/** "manual" or the id of a location module. */
	source: string;
	status: 'applied' | 'undone';
}

export interface AssetDetail {
	id: string;
	type: string;
	file_name: string;
	local_taken_at: string;
	taken_at: string | null;
	time_zone: string | null;
	camera_make: string | null;
	camera_model: string | null;
	lens_model: string | null;
	width: number | null;
	height: number | null;
	latitude: number | null;
	longitude: number | null;
	city: string | null;
	state: string | null;
	country: string | null;
	review_status: ReviewStatus;
	albums: string[];
	/** Newest first. */
	location_history: LocationChange[];
	/** The last write replaced earlier coordinates, so it can be undone. */
	can_undo: boolean;
	previous_id: string | null;
	next_id: string | null;
	/** The photo in the Immich web UI. */
	immich_url: string | null;
	/** Changes with the thumbnails (photo rotated or edited in Immich). */
	version: string | null;
}

export interface MapConfig {
	style_url: string;
	geocoder_enabled: boolean;
}

export interface Place {
	name: string;
	label: string;
	latitude: number;
	longitude: number;
	kind: string | null;
}

export interface NeighborEvidence {
	asset_id: string;
	file_name: string;
	/** Seconds from the photo; negative means before it. */
	delta_s: number;
	/** Time neighbors only. */
	same_camera?: boolean;
	/** The neighbor's location was written by this app, not recorded by a camera. */
	estimated: boolean;
	/** Similar photos only: 0..1, and when the photo was taken (local time). */
	similarity?: number;
	local_taken_at?: string;
}

export interface Candidate {
	/** 1-based rank within the module. */
	rank: number;
	latitude: number;
	longitude: number;
	/** 0..1, comparable only within one module. */
	score: number;
	radius_m: number | null;
	kind: string;
	evidence: { neighbors?: NeighborEvidence[]; share?: number } & Record<string, unknown>;
	/** weak: shown folded ("probably only the region is right"); confident: marked as such. */
	tier: 'weak' | 'normal' | 'confident';
}

export interface TrackPoint extends NeighborEvidence {
	latitude: number;
	longitude: number;
	local_taken_at: string;
	/** Camera as shown to the user ("" when unknown). */
	camera: string;
	role: 'before' | 'after' | null;
}

export interface CameraCount {
	/** Camera filter value (make + separator + model). */
	value: string;
	label: string;
	count: number;
	same_camera: boolean;
	excluded: boolean;
}

export interface ModuleSuggestions {
	module: string;
	version: string;
	color: string;
	shape: string;
	candidates: Candidate[];
	track: TrackPoint[];
	/** Cameras of the photos the module looked at; the user may exclude some. */
	cameras: CameraCount[];
	/** Why there are no candidates (e.g. "scanner"). */
	note: string | null;
	/** ready: computed now (core modules); the others describe the latest run of a worker module. */
	status: ModuleStatus;
	/** Run by workers: can be started (again) from the card. */
	runnable: boolean;
	/** A worker running this module has contacted the core recently. */
	worker_available: boolean;
	error: string | null;
	/** Why the latest run failed (see FAILURE_CODES). */
	error_code: string | null;
	finished_at: string | null;
	/** Queued runs: jobs of the module a worker takes before this one. */
	queue_position: number | null;
	/** Background runs of the module are paused; a run started from the card still goes. */
	paused: boolean;
	/** A worker of the module is downloading or loading its model: the next run takes longer. */
	worker_loading: boolean;
	/** Tells the blocks apart: the module id, or "<module>:region" for its run on a part. */
	key: string;
	/** The part of the photo of a run on a part (FR-35). */
	region: Region | null;
	/** The run was on the photo turned this way. */
	turn: Turn;
}

/** A part of the photo as shares of its width and height (of the photo as shown). */
export interface Region {
	x: number;
	y: number;
	w: number;
	h: number;
}

export type ModuleStatus = 'ready' | 'not_run' | 'queued' | 'running' | 'done' | 'failed';

export const isPending = (module: ModuleSuggestions) =>
	module.status === 'queued' || module.status === 'running';

export interface WorkerInfo {
	name: string;
	device: string;
	modules: string[];
	version: string;
	last_seen_at: string;
	active: boolean;
	/** What it says it is doing, while connected; null for older workers. */
	state: WorkerState | null;
	state_module: string | null;
	state_since: string | null;
}

export type WorkerState = 'idle' | 'busy' | 'downloading' | 'loading' | 'working';

export interface WorkersOverview {
	workers: WorkerInfo[];
	/** Module -> status of the latest run -> number of photos. */
	runs: Record<string, Partial<Record<ModuleStatus, number>>>;
	/** Module -> failure code -> photos whose latest run failed so. */
	failures: Record<string, Record<string, number>>;
	auto_modules: string[];
	/** Indexing module -> photos with a location in its search index, of those it indexes. */
	index: Record<string, { indexed: number; located: number }>;
	pause: Pause;
}

/** Paused background runs, for the whole installation: of every module, or of these. */
export interface Pause {
	all: boolean;
	modules: string[];
}

export const getWorkers = () => request<WorkersOverview>('GET', '/api/library/workers');

export const getPause = () => request<Pause>('GET', '/api/library/pause');
/** Pauses or resumes a module; `null` stands for all modules together. */
export const setPause = (module: string | null, paused: boolean) =>
	request<Pause>('PUT', '/api/library/pause', { module, paused });
/** Resumes every module, paused one by one or all together. */
export const resumeAll = () => request<Pause>('DELETE', '/api/library/pause');

/** Runs the module again on the photos whose latest run failed (for this reason). */
export const rerunFailed = (module: string, code: string | null) =>
	request<{ queued: number }>('POST', `/api/library/modules/${module}/rerun-failed`, { code });

function cameraQuery(excludeCameras: string[], sameCameraOnly = false): string {
	const params = new URLSearchParams(excludeCameras.map((value) => ['exclude_camera', value]));
	if (sameCameraOnly) params.set('same_camera_only', 'true');
	return params.size ? `?${params}` : '';
}

export const getSuggestions = (id: string, excludeCameras: string[] = [], sameCameraOnly = false) =>
	request<ModuleSuggestions[]>(
		'GET',
		`/api/assets/${id}/suggestions${cameraQuery(excludeCameras, sameCameraOnly)}`
	);

/** Queues a worker module for the photo, or a part of it, ahead of the background runs. */
export const runModule = (
	id: string,
	module: string,
	excludeCameras: string[] = [],
	region: Region | null = null,
	sameCameraOnly = false,
	turn: Turn = 0
) =>
	request<ModuleSuggestions[]>(
		'POST',
		`/api/assets/${id}/modules/${module}/run${cameraQuery(excludeCameras, sameCameraOnly)}`,
		{ turn, ...(region ? { region } : {}) }
	);
export const getAsset = (id: string, filter: GalleryFilter) =>
	request<AssetDetail>('GET', `/api/assets/${id}${filterQuery(filter)}`);
export const setReview = (id: string, status: ReviewStatus, filter: GalleryFilter) =>
	request<AssetDetail>('PUT', `/api/assets/${id}/review${filterQuery(filter)}`, { status });
export const setLocation = (
	id: string,
	point: { lat: number; lon: number },
	filter: GalleryFilter | null = null,
	keepalive = false
) =>
	request<AssetDetail>(
		'PUT',
		`/api/assets/${id}/location${filter ? filterQuery(filter) : ''}`,
		{ latitude: point.lat, longitude: point.lon },
		keepalive
	);
/** Saves the photo rotated in Immich, on top of how it is shown now (an Immich edit). */
export const rotateInImmich = (id: string, turn: Turn, filter: GalleryFilter) =>
	request<AssetDetail>('POST', `/api/assets/${id}/rotate${filterQuery(filter)}`, { turn });

export const undoLocation = (id: string, filter: GalleryFilter | null = null) =>
	request<AssetDetail>(
		'POST',
		`/api/assets/${id}/location/undo${filter ? filterQuery(filter) : ''}`
	);
export const getMapConfig = () => request<MapConfig>('GET', '/api/config/map');
export function geocode(q: string, lang: string, near: { lat: number; lon: number } | null) {
	const params = new URLSearchParams({ q, lang });
	if (near) {
		params.set('lat', String(near.lat));
		params.set('lon', String(near.lon));
	}
	return request<Place[]>('GET', `/api/geocode?${params}`);
}

export const getHealth = () => request<Health>('GET', '/api/health');
export const getLibrary = () => request<Library>('GET', '/api/library');
export const startSync = (full: boolean | null = null) =>
	request<Job>('POST', '/api/library/sync', { full });
export const login = (apiKey: string) =>
	request<Me>('POST', '/api/auth/login', { api_key: apiKey });
export const loginWithPassword = (email: string, password: string) =>
	request<Me>('POST', '/api/auth/login/password', { email, password });
export const logout = () => request<void>('POST', '/api/auth/logout');
export const getMe = () => request<Me>('GET', '/api/auth/me');
