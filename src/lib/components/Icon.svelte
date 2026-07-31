<script>
  let { name } = $props();
</script>

<svg viewBox="0 0 24 24" aria-hidden="true">
  {#if name === "share"}
    <path d="M8 12 16 7M8 13l8 4M18 4a3 3 0 1 0 0 6 3 3 0 0 0 0-6ZM6 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm12 8a3 3 0 1 0 0 6 3 3 0 0 0 0-6Z"/>
  {:else if name === "external"}
    <path d="M14 4h6v6M20 4l-9 9M18 13v7H4V6h7"/>
  {:else if name === "locate"}
    <path d="M12 3v3M12 18v3M3 12h3M18 12h3M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Z"/>
  {:else if name === "copy"}
    <path d="M8 8h11v12H8zM5 16H4V4h11v1"/>
  {:else if name === "report"}
    <!-- Same megaphone the Report route carries in the nav, so the map action
         and the destination it opens are recognisably the same thing. -->
    <path d="M4 13v-2l13-5v12L4 13Zm0 0v6h4l2-5M17 9h3M18 5l2-2M18 19l2 2"/>
  {:else if name === "alert"}
    <path d="M12 4.5 2.8 20h18.4L12 4.5ZM12 10v4.5M12 17.4v.2"/>
  {:else if name === "level"}
    <!-- A gauge staff standing in water: the bulletin's calm and warning states
         are both readings off the same instrument. -->
    <path d="M8 3v13M5.5 6.5h5M5.5 10h5M5.5 13.5h5M2 19c2.2-1.6 3.6-1.6 5.8 0s3.6 1.6 5.8 0 3.6-1.6 5.4-.6"/>
  {:else if name === "no-reading"}
    <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18ZM8.5 12h7"/>
  {:else if name === "falling"}
    <path d="M12 5v13M6.5 12.5 12 18l5.5-5.5"/>
  {:else if name === "rising"}
    <path d="M12 19V6M6.5 11.5 12 6l5.5 5.5"/>
  {:else if name === "steady"}
    <path d="M5 12h14M5 8h14M5 16h14"/>
  {:else if name === "chevron"}
    <path d="m6.5 9.5 5.5 5.5 5.5-5.5"/>
  {/if}
</svg>
