<!--
  THESIS: A resident, a journalist, or an agency asking "what is this site and
  what is it promising me?" gets one answer here, in words they can read.
  MODE: Preserve the River Observatory visual system. Legal content that a
  stressed person can still parse, because the whole point of the page is the
  sentence "do not make a serious decision from this site alone".

  The disclaimer, the liability limit, and the reuse terms live together on one
  page rather than three. Someone checking what we promise should not have to
  find three documents to learn we promise very little.
-->
<script>
  const UPDATED = "1 August 2026";
</script>

<article class="terms">
  <header class="terms-head">
    <p class="terms-kicker">Axom Flood</p>
    <h1>Terms of use</h1>
    <p class="terms-lede">
      What this site is, where its numbers come from, and what it does not promise.
    </p>
    <p class="terms-updated">Last updated {UPDATED}</p>
  </header>

  <aside class="terms-summary" aria-labelledby="summary-heading">
    <h2 id="summary-heading">The short version</h2>
    <ul>
      <li>Every reading here is copied from a government source. We do not measure rivers ourselves.</li>
      <li>This is not an official warning. It does not replace CWC, ASDMA, or your district administration.</li>
      <li>Data can be old, missing, or wrong.</li>
      <li><strong>Do not decide whether to evacuate, travel, or move property based on this site alone.</strong> Follow official instructions and call ASDMA on <a href="tel:1070">1070</a>.</li>
    </ul>
  </aside>

  <section class="terms-section">
    <h2>What Axom Flood is</h2>
    <p>
      Axom Flood is a free, open-source website. It takes river and flood data that
      Indian government agencies already publish, and rewrites it in plain language
      so an ordinary person can read it quickly.
    </p>
    <p>
      That is the whole job. We translate. We do not forecast, we do not issue
      warnings, and we have no authority to tell anyone to do anything.
    </p>
  </section>

  <section class="terms-section">
    <h2>Where the numbers come from</h2>
    <p>
      River levels come from the Central Water Commission (CWC). Flood impact
      figures, relief camp listings, and bulletins come from the Assam State
      Disaster Management Authority (ASDMA) and its district offices. Boundaries
      and place names come from OpenStreetMap and the Census of India.
      <a href="/about/">The about page</a> lists each source and its current state.
    </p>
    <p>
      We do not own this data and we do not change the values in it. If an
      official source publishes a number, we show that number. If an official
      source is wrong, this site will be wrong in the same way.
    </p>
  </section>

  <section class="terms-section">
    <h2>Do not make serious decisions from this site</h2>
    <p>
      Decisions about evacuating, staying, travelling, moving livestock, or moving
      property are safety-of-life decisions. Make them on instructions from the
      authorities responsible for your area, not from a website that is reading
      the same public feeds you could read yourself.
    </p>
    <p>
      In an emergency, call ASDMA on <a href="tel:1070">1070</a> and follow whatever
      the local administration tells you. If this site and an official instruction
      disagree, the official instruction is correct.
    </p>
  </section>

  <section class="terms-section">
    <h2>The data can be wrong, old, or missing</h2>
    <p>
      Sources go down. Feeds freeze. A gauge stops reporting and nobody announces
      it. When we can tell that a reading is old or absent, we say so on the screen
      rather than filling the gap with a guess. But we cannot always tell.
    </p>
    <p>
      Some things on this site are explicitly unverified, and are labelled that way
      where they appear: relief camp locations, the mapping of gauges to revenue
      circles, and the Assamese translations. Treat anything marked unreviewed as a
      starting point for a phone call, not as a fact.
    </p>
  </section>

  <section class="terms-section">
    <h2>Reports sent from this site</h2>
    <p>
      If you use the report screen, the water depth you choose and your device's
      location are saved and sent to us. Do not send anything you would not want
      recorded. Reports from the public never change the official river status
      shown on this site, and they are not verified.
    </p>
  </section>

  <section class="terms-section">
    <h2>No warranty</h2>
    <p>
      This site is provided "as is" and "as available", with no warranty of any
      kind, express or implied. We do not warrant that it is accurate, complete,
      current, uninterrupted, or fit for any particular purpose. You use it at your
      own risk.
    </p>
  </section>

  <section class="terms-section">
    <h2>Limitation of liability</h2>
    <p>
      To the fullest extent permitted by law, the people who make and run Axom
      Flood are not liable for any loss, injury, damage, or cost arising from your
      use of this site, from anything you did or did not do because of it, or from
      any error, delay, or unavailability in it or in the government sources it
      reads.
    </p>
    <p>
      Nothing here limits any liability that cannot lawfully be limited.
    </p>
  </section>

  <section class="terms-section">
    <h2>Reusing the code and the data</h2>
    <p>
      The source code is open and licensed under the GNU Affero General Public
      License v3.0. You can read it, run it, and build on it under that licence.
    </p>
    <p>
      The underlying data is not ours to license. Government data stays with the
      agency that published it, on that agency's terms. Boundary and place-name
      data from OpenStreetMap is © OpenStreetMap contributors and available under
      the Open Database License, and anything you build from it must keep that
      attribution.
    </p>
  </section>

  <section class="terms-section">
    <h2>Changes and contact</h2>
    <p>
      These terms can change. The date at the top says when they last did.
      Questions, corrections, and reports of a wrong number are welcome on the
      <a href="https://github.com/Shady-2096/axom-flood" rel="noopener" target="_blank">project's GitHub page</a>.
    </p>
  </section>

  <nav class="terms-links" aria-label="Related">
    <a href="/">Check Assam rivers</a>
    <a href="/about/">About this site</a>
    <a href="/emergency/">Emergency contacts</a>
  </nav>
</article>

<style>
  .terms {
    max-width: 720px;
    margin: 0 auto;
    padding: 40px 0 56px;
  }

  .terms-head {
    padding-bottom: 32px;
    border-bottom: 1px solid var(--line);
  }

  .terms-kicker {
    margin: 0;
    color: var(--river);
    font-size: 12px;
    font-weight: 800;
    letter-spacing: .08em;
    text-transform: uppercase;
  }

  h1 {
    margin: 12px 0 0;
    color: var(--ink);
    font-size: 28px;
    letter-spacing: -.02em;
  }

  .terms-lede {
    margin: 12px 0 0;
    color: var(--muted);
    font-size: 18px;
  }

  .terms-updated {
    margin: 16px 0 0;
    color: var(--muted);
    font-size: 12px;
  }

  /* The one block someone skimming in an emergency will actually read, so it
     carries the evacuation sentence rather than burying it in section four. */
  .terms-summary {
    margin: 32px 0 0;
    padding: 24px;
    border-left: 4px solid var(--river);
    border-radius: var(--r-panel);
    background: var(--veil);
  }

  .terms-summary h2 {
    margin: 0;
    color: var(--ink);
    font-size: 16px;
  }

  .terms-summary ul {
    margin: 12px 0 0;
    padding-left: 20px;
    color: var(--ink);
  }

  .terms-summary li + li {
    margin-top: 8px;
  }

  .terms-section {
    margin-top: 40px;
  }

  .terms-section h2 {
    margin: 0;
    color: var(--ink);
    font-size: 20px;
    letter-spacing: -.01em;
  }

  .terms-section p {
    margin: 12px 0 0;
    color: var(--graphite);
    font-size: 16px;
    line-height: 1.65;
  }

  .terms-links {
    display: flex;
    flex-wrap: wrap;
    gap: 12px 24px;
    margin-top: 56px;
    padding-top: 24px;
    border-top: 1px solid var(--line);
  }

  .terms-links a {
    color: var(--graphite);
  }

  @media (max-width: 560px) {
    .terms {
      padding: 24px 0 40px;
    }

    .terms-summary {
      padding: 20px;
    }

    .terms-links {
      display: grid;
    }
  }
</style>
