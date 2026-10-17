<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<script lang="ts">
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale, locales, setLocale, type Locale } from '#lib/paraglide/runtime.js';

	// Language names are shown in their own language, so they are not translated.
	const names: Record<Locale, string> = { en: 'English', ru: 'Русский' };
</script>

<label>
	{m.language()}
	<select value={getLocale()} onchange={(event) => setLocale(event.currentTarget.value as Locale)}>
		{#each locales as locale (locale)}
			<option value={locale}>{names[locale]}</option>
		{/each}
	</select>
</label>
