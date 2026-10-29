<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- When the header is too narrow (a phone, a narrow window), what does not fit goes into this
     menu: the language, the theme and signing out, and on a phone the pages too. Which parts show
     is decided by the width alone, in the styles of the header. Closes on a click outside, on Esc
     and on going to a page. -->
<script lang="ts">
	import { LANGUAGE_NAMES } from '#lib/languages.js';
	import { m } from '#lib/paraglide/messages.js';
	import { getLocale, locales, setLocale, type Locale } from '#lib/paraglide/runtime.js';
	import ThemeSwitcher from '#lib/ThemeSwitcher.svelte';
	import Icon from '#lib/ui/Icon.svelte';

	interface Page {
		href: string;
		label: string;
		current: boolean;
	}

	let {
		pages,
		user,
		onsignout
	}: {
		pages: Page[];
		user: string;
		onsignout: () => void;
	} = $props();

	let open = $state(false);
	let root: HTMLDivElement | undefined = $state();
	const current = getLocale();

	function closeOutside(event: PointerEvent) {
		if (open && root && !root.contains(event.target as Node)) open = false;
	}

	function closeOnEscape(event: KeyboardEvent) {
		if (!open || event.key !== 'Escape') return;
		event.preventDefault();
		open = false;
		root?.querySelector('button')?.focus();
	}
</script>

<svelte:window onpointerdown={closeOutside} onkeydown={closeOnEscape} />

<div class="st-headmenu" bind:this={root}>
	<button
		type="button"
		class="st-iconbtn"
		aria-haspopup="true"
		aria-expanded={open}
		aria-label={m.nav_menu()}
		title={m.nav_menu()}
		onclick={() => (open = !open)}
	>
		<Icon name="menu" size={18} />
	</button>
	{#if open}
		<div class="st-menu st-headmenu__panel">
			<nav class="st-headmenu__pages">
				<!-- eslint-disable svelte/no-navigation-without-resolve -- resolved by the layout -->
				{#each pages as page (page.href)}
					<a
						class="st-menu__item"
						href={page.href}
						aria-current={page.current ? 'page' : undefined}
						data-active={page.current}
						onclick={() => (open = false)}
					>
						<span class="st-menu__label">{page.label}</span>
					</a>
				{/each}
				<!-- eslint-enable svelte/no-navigation-without-resolve -->
				<div class="st-menu__sep"></div>
			</nav>
			<label class="st-menu__heading" for="st-headmenu-language">{m.language()}</label>
			<div class="st-input st-input--sm st-headmenu__row">
				<Icon name="languages" size={14} />
				<select
					id="st-headmenu-language"
					value={current}
					onchange={(event) => setLocale(event.currentTarget.value as Locale)}
				>
					{#each locales as locale (locale)}
						<option value={locale} lang={locale}>{LANGUAGE_NAMES[locale]}</option>
					{/each}
				</select>
			</div>
			<div class="st-menu__heading">{m.theme()}</div>
			<div class="st-headmenu__row">
				<ThemeSwitcher />
			</div>
			<div class="st-menu__sep"></div>
			<div class="st-menu__heading st-headmenu__user">{user}</div>
			<button type="button" class="st-menu__item" onclick={onsignout}>
				<Icon name="log-out" size={14} />
				<span class="st-menu__label">{m.auth_sign_out()}</span>
			</button>
		</div>
	{/if}
</div>
