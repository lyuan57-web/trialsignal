(function () {
  const data = window.TRIALSIGNAL_DEMO_DATA;
  if (!data) return;

  const parse = (value) => {
    try { return JSON.parse(value || "[]"); } catch (_) { return []; }
  };
  const normalize = (value) => String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  const jaccard = (left, right) => {
    const a = new Set(left || []), b = new Set(right || []);
    if (!a.size || !b.size) return 0;
    let overlap = 0;
    a.forEach((value) => { if (b.has(value)) overlap += 1; });
    return overlap / new Set([...a, ...b]).size;
  };
  const same = (left, right) => left && left === right ? 1 : 0;
  const conditionSimilarity = (left, right) => {
    const labelOverlap = jaccard(left, right);
    const tokens = (values) => [...new Set((values || []).flatMap((value) => normalize(value).split(" ")).filter(Boolean))];
    return Math.max(labelOverlap, jaccard(tokens(left), tokens(right)));
  };

  function search(params) {
    const condition = normalize(params.get("condition"));
    const sponsor = normalize(params.get("sponsor"));
    const status = String(params.get("status") || "").toUpperCase();
    const phase = String(params.get("phase") || "").toUpperCase();
    const country = normalize(params.get("country"));
    const type = String(params.get("study_type") || "").toUpperCase();
    const limit = Math.min(Math.max(Number(params.get("limit") || 50), 1), 200);
    return data.trials.filter((row) => {
      const conditionText = normalize(`${row.conditions.join(" ")} ${row.title}`);
      return (!condition || conditionText.includes(condition)) &&
        (!sponsor || normalize(row.sponsor).includes(sponsor)) &&
        (!status || row.overall_status === status) &&
        (!phase || parse(row.phases).includes(phase)) &&
        (!country || parse(row.countries).some((item) => normalize(item).includes(country))) &&
        (!type || row.study_type === type);
    }).slice(0, limit);
  }

  function countries(params) {
    const filtered = search(new URLSearchParams({
      condition: params.get("condition") || "",
      limit: "200"
    }));
    const counts = new Map();
    filtered.forEach((row) => parse(row.countries).forEach((country) =>
      counts.set(country, (counts.get(country) || 0) + 1)));
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .map(([country, trial_count]) => ({ country, trial_count }));
  }

  function comparables(nctId, limit) {
    const target = data.trials.find((row) => row.nct_id === nctId);
    if (!target) throw new Error(`Unknown trial: ${nctId}`);
    return data.trials.filter((row) => row.nct_id !== nctId).map((row) => {
      const enrollment = target.enrollment_count != null && row.enrollment_count != null
        ? Math.exp(-Math.abs(Math.log1p(target.enrollment_count) - Math.log1p(row.enrollment_count)))
        : 0;
      const components = {
        condition_overlap: [conditionSimilarity(target.conditions, row.conditions), 0.30],
        phase_overlap: [jaccard(parse(target.phases), parse(row.phases)), 0.12],
        intervention_type_overlap: [jaccard(target.intervention_types, row.intervention_types), 0.12],
        geography_overlap: [jaccard(parse(target.countries), parse(row.countries)), 0.10],
        same_sponsor_class: [same(target.sponsor_class, row.sponsor_class), 0.04],
        same_primary_purpose: [same(target.primary_purpose, row.primary_purpose), 0.06],
        same_intervention_model: [same(target.intervention_model, row.intervention_model), 0.06],
        same_allocation: [same(target.allocation, row.allocation), 0.04],
        same_masking: [same(target.masking, row.masking), 0.04],
        enrollment_scale_similarity: [enrollment, 0.12]
      };
      const similarity = Object.values(components).reduce((sum, [value, weight]) => sum + value * weight, 0);
      return {
        nct_id: row.nct_id,
        title: row.title,
        sponsor: row.sponsor,
        status: row.overall_status,
        similarity: Number(similarity.toFixed(4)),
        evidence: Object.fromEntries(Object.entries(components).map(([name, [value, weight]]) =>
          [name, { value: Number(value.toFixed(4)), weight }]))
      };
    }).sort((a, b) => b.similarity - a.similarity).slice(0, limit);
  }

  window.trialSignalDemoApi = async function (path) {
    const url = new URL(path, window.location.origin);
    if (url.pathname === "/quality") return data.quality;
    if (url.pathname === "/benchmarks/duration") return data.duration;
    if (url.pathname === "/trials/search") return search(url.searchParams);
    if (url.pathname === "/landscape/countries") return countries(url.searchParams);
    let match = url.pathname.match(/^\/trials\/([^/]+)\/comparables$/);
    if (match) return comparables(decodeURIComponent(match[1]), Number(url.searchParams.get("limit") || 10));
    match = url.pathname.match(/^\/trials\/([^/]+)\/risk$/);
    if (match) {
      const nctId = decodeURIComponent(match[1]);
      const probability = data.risk_probabilities[nctId];
      if (probability == null) throw new Error(`No benchmark available for ${nctId}`);
      return { nct_id: nctId, adverse_outcome_probability: probability, ...data.risk_model };
    }
    throw new Error(`Static demo route is unavailable: ${url.pathname}`);
  };

  document.addEventListener("DOMContentLoaded", () => {
    const env = document.querySelector(".env");
    if (env) env.textContent = "Public demo snapshot";
    const source = document.querySelector(".source");
    if (source) source.innerHTML = `<strong>Source coverage</strong>${data.metadata.demo_record_count.toLocaleString()} curated records<br>${data.metadata.source_record_count.toLocaleString()} records processed by full pipeline`;
    const docs = document.querySelector(".top-link");
    if (docs) {
      docs.textContent = "View source on GitHub";
      docs.href = "https://github.com/lyuan57-web/trialsignal";
      docs.target = "_blank";
      docs.rel = "noopener";
    }
  });
})();
