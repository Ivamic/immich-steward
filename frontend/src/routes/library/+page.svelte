<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- The page was called Library before 0.3.2: old bookmarks go to Processing. -->
<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';

	$effect(() => {
		goto(resolve('/processing'), { replaceState: true });
	});
</script>
