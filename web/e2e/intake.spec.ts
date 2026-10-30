import { expect, test } from "@playwright/test";
import path from "node:path";

const fixtures = path.resolve(process.env.PDTL_BROWSER_INPUTS!);

async function uploadAndSelect(page: import('@playwright/test').Page) {
  // Matching counts can belong to the previous delivery while upload is in flight.
  const marker = page.locator('#intake-receipt-detail > p.iw-eyebrow');
  const previous = await marker.count() ? await marker.textContent() : '';
  await page.getByRole('button', { name: 'Upload and preview' }).click();
  await expect(marker).toBeVisible();
  await expect(marker).not.toHaveText(previous ?? '');
}


test("imports XLSX and CSV, quarantines, preserves repeats, verifies and reopens location work", async ({
  page,
}, info) => {
  const scope = `clinic-${info.project.name}`;
  await page.goto("/?view=intake");
  await page.getByLabel("Source namespace", { exact: true }).fill(scope);
  await page
    .getByLabel("Source file", { exact: true })
    .setInputFiles(path.join(fixtures, "synthetic-clinic.xlsx"));
  await uploadAndSelect(page);
  await expect(
    page.getByText(
      "Headers must be nonblank and unique; choose another header row",
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByLabel("Header row", { exact: true }).fill("2");
  await page
    .getByRole("button", { name: "Save mapping and reprocess" })
    .click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Map required fields:" }),
  ).toBeVisible();
  const mapping: Record<string, string> = {
    npi: "Registry number",
    provider_name: "Clinician",
    address: "Street",
    city: "Town",
    state: "Region",
    zip: "Postal",
    phone: "Listed phone",
    record_id: "Roster key",
    location_id: "Site key",
    reference_phone: "Requested phone",
  };
  for (const [field, column] of Object.entries(mapping)) {
    await page
      .getByLabel(
        new RegExp(
          `^${field.replaceAll("_", " ")} \\*|^${field.replaceAll("_", " ")} \\(optional\\)`,
        ),
      )
      .selectOption(column);
  }
  await page
    .getByRole("button", { name: "Save mapping and reprocess" })
    .click();
  await expect(
    page.getByText("2 valid · 1 quarantined · 3 total"),
  ).toBeVisible();
  await page.getByText("Clinic roster!3 · Valid", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Original evidence", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".iw-preview").getByText("02108", { exact: false }).first()).toBeVisible();
  await page
    .getByLabel("Reviewer", { exact: true })
    .first()
    .fill("Synthetic Reviewer");
  await page
    .getByLabel("Acceptance / rejection reason")
    .fill("Accept two valid sites; retain malformed evidence");
  await page.getByRole("button", { name: "Accept valid rows" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Source observations and relationships",
    }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("intake-xlsx-accepted.png"),
    fullPage: true,
  });

  // A second shape maps directly into the same source model, then repeats without duplicate work.
  await page
    .getByLabel("Source file", { exact: true })
    .setInputFiles(path.join(fixtures, "synthetic-clinic.csv"));
  await uploadAndSelect(page);
  await expect(
    page.getByText("2 valid · 0 quarantined · 2 total"),
  ).toBeVisible();
  await page
    .getByLabel("Reviewer", { exact: true })
    .first()
    .fill("Synthetic Reviewer");
  await page
    .getByLabel("Acceptance / rejection reason")
    .fill("CSV same sites with native identity");
  await page.getByRole("button", { name: "Accept valid rows" }).click();
  await expect(
    page.getByRole("heading", { name: "Linked cases" }),
  ).toBeVisible();
  await uploadAndSelect(page);
  await expect(page.getByText(/Repeat delivery of/)).toBeVisible();
  await page
    .getByLabel("Reviewer", { exact: true })
    .first()
    .fill("Synthetic Reviewer");
  await page
    .getByLabel("Acceptance / rejection reason")
    .fill("Record repeat delivery");
  await page.getByRole("button", { name: "Accept valid rows" }).click();
  await expect(
    page.getByText("duplicate delivery", { exact: true }),
  ).toBeVisible();

  await page.goto("/?view=work");
  await page.getByLabel("Search work").fill(scope);
  const cases = page.locator(".iw-list li button");
  await expect(cases).toHaveCount(2);
  for (let index = 0; index < 2; index++) {
    await cases.nth(index).click();
    const location = index === 0 ? "NORTH" : "SOUTH";
    await expect(
      page.getByText(`${scope}:${location} · new`, { exact: true }),
    ).toBeVisible();
    const values = {
      proposal: index === 0 ? "6175550199" : "6175550198",
      observed: index === 0 ? "6175550199" : "6175550170",
    };
    for (const action of ["triage", "approve", "submit", "verify"]) {
      await page
        .getByRole("combobox", { name: "Action", exact: true })
        .selectOption(action);
      await page
        .getByLabel("actor *", { exact: true })
        .fill("Synthetic Reviewer");
      await page
        .getByLabel("reason *", { exact: true })
        .fill(`Synthetic ${action} evidence`);
      if (action === "approve")
        await page
          .getByLabel("proposal *", { exact: true })
          .fill(values.proposal);
      if (action === "submit")
        await page
          .getByLabel("submission reference *", { exact: true })
          .fill("SIMULATED-TICKET");
      if (action === "verify") {
        await page
          .getByLabel("observed *", { exact: true })
          .fill(values.observed);
        await page
          .getByLabel("verification note *", { exact: true })
          .fill("Manually observed synthetic portal response");
      }
      await page.getByRole("button", { name: "Save review event" }).click();
      await expect(page.getByLabel("reason *", { exact: true })).toHaveValue(
        "",
      );
    }
    await expect(
      page.getByText(
        `${scope}:${location} · ${index === 0 ? "verified" : "reopened"}`,
        { exact: true },
      ),
    ).toBeVisible();
  }
  await page.screenshot({
    path: info.outputPath("intake-work-reopened.png"),
    fullPage: true,
  });
  await page.reload();
  await expect(page.getByLabel("Search work")).toHaveValue(scope);
  await expect(page.locator(".iw-list li button")).toHaveCount(2);
  await page.goto("/?view=intake");
  await page.getByLabel("Source namespace", { exact: true }).fill(scope);
  await page
    .getByLabel("Source file", { exact: true })
    .setInputFiles(path.join(fixtures, "synthetic-clinic.xlsx"));
  await uploadAndSelect(page);
  await expect(
    page.getByText("2 valid · 1 quarantined · 3 total"),
  ).toBeVisible();
  await expect(page.getByText(/Repeat delivery of/)).toBeVisible();
  await page
    .getByLabel("Reviewer", { exact: true })
    .first()
    .fill("Synthetic Reviewer");
  await page
    .getByLabel("Acceptance / rejection reason")
    .fill("Workbook repeat preserves completed work");
  await page.getByRole("button", { name: "Accept valid rows" }).click();
  await expect(
    page.getByText("duplicate delivery", { exact: true }),
  ).toBeVisible();
  await page
    .getByLabel("Source file", { exact: true })
    .setInputFiles(path.join(fixtures, "synthetic-changed.csv"));
  await uploadAndSelect(page);
  await page
    .getByText("Comparison with prior source deliveries", { exact: true })
    .click();
  await expect(
    page.locator("pre").filter({ hasText: '"changed": 1' }).first(),
  ).toBeVisible();
  await page
    .getByLabel("Reviewer", { exact: true })
    .first()
    .fill("Synthetic Reviewer");
  await page
    .getByLabel("Acceptance / rejection reason")
    .fill("Later evidence cannot overwrite human decisions");
  await page.getByRole("button", { name: "Accept valid rows" }).click();
  await expect(
    page.getByRole("heading", { name: "Linked cases" }),
  ).toBeVisible();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Evidence packet JSON" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("evidence-packet.json");
  const packet = JSON.parse(
    await (
      await import("node:fs/promises")
    ).readFile((await download.path())!, "utf8"),
  );
  expect(packet.cases).toHaveLength(2);
  expect(packet.cases.map((c: { status: string }) => c.status).sort()).toEqual([
    "reopened",
    "verified",
  ]);
  expect(
    packet.cases.every((c: { history: unknown[] }) => c.history.length === 4),
  ).toBeTruthy();
  await page.screenshot({
    path: info.outputPath("intake-later-evidence.png"),
    fullPage: true,
  });
});

test("saved public responses, failures, retry, keyboard and responsive sources", async ({
  page,
}, info) => {
  await page.goto("/?view=intake");
  await page
    .getByLabel("Source namespace", { exact: true })
    .fill(`offline-${info.project.name}`);
  await page.getByLabel("Response profile").selectOption("nppes");
  await page
    .getByLabel("Source file", { exact: true })
    .setInputFiles(path.join(fixtures, "synthetic-nppes.json"));
  await uploadAndSelect(page);
  await expect(
    page.getByText("1 valid · 0 quarantined · 1 total"),
  ).toBeVisible();
  await page
    .getByLabel("Reviewer", { exact: true })
    .first()
    .fill("Synthetic Reviewer");
  await page
    .getByLabel("Acceptance / rejection reason")
    .fill("Offline NPPES contract replay");
  await page.getByRole("button", { name: "Accept valid rows" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Source observations and relationships",
    }),
  ).toBeVisible();
  const observation = page
    .locator("details")
    .filter({
      has: page.locator("button").filter({hasText: "Link observation explicitly"}),
    })
    .first();
  await observation.locator("summary").first().click();
  await observation
    .getByRole("combobox", { name: "Native source location", exact: true })
    .selectOption("1");
  await observation
    .getByLabel("Provider identity", { exact: true })
    .fill("NPI:1234567890");
  await observation
    .getByLabel("Local location identity", { exact: true })
    .fill(`offline-${info.project.name}:reviewed-site`);
  await observation
    .getByLabel("Reviewer", { exact: true })
    .fill("Synthetic Reviewer");
  await observation
    .getByLabel("Relationship evidence / reason")
    .fill("Selected second synthetic practice address");
  await observation
    .getByRole("button", { name: "Link observation explicitly" })
    .click();
  await expect(observation.locator("pre").first()).toContainText(
    '"location_index": 1',
  );
  await page.getByLabel("Response profile").selectOption("cms");
  await page
    .getByLabel("Source file", { exact: true })
    .setInputFiles(path.join(fixtures, "synthetic-cms.json"));
  await uploadAndSelect(page);
  await expect(
    page.getByText("1 valid · 0 quarantined · 1 total"),
  ).toBeVisible();
  await page
    .getByLabel("Reviewer", { exact: true })
    .first()
    .fill("Synthetic Reviewer");
  await page
    .getByLabel("Acceptance / rejection reason")
    .fill("Offline CMS enrollment/address replay");
  await page.getByRole("button", { name: "Accept valid rows" }).click();
  await expect(
    page.getByRole("heading", {
      name: "Source observations and relationships",
    }),
  ).toBeVisible();
  await page
    .getByLabel("Source file", { exact: true })
    .setInputFiles({
      name: "broken.json",
      mimeType: "application/json",
      buffer: Buffer.from("{"),
    });
  await uploadAndSelect(page);
  await expect(
    page.getByText("Invalid UTF-8 JSON payload", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Save mapping and reprocess" })
    .click();
  await expect(
    page.getByText("Invalid UTF-8 JSON payload", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: info.outputPath("intake-failed-retry.png"),
    fullPage: true,
  });
  const sources = page.getByRole("link", { name: "Sources", exact: true });
  await sources.focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { name: "Source registry" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: info.outputPath("intake-sources.png"),
    fullPage: true,
  });
  await page.route("**/api/work", (route) =>
    route.fulfill({
      status: 503,
      body: JSON.stringify({ detail: "Synthetic service unavailable" }),
    }),
  );
  await page.getByRole("link", { name: "Work queue", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Synthetic service unavailable",
  );
  await page.unroute("**/api/work");
  await page.getByRole("button", { name: "Retry / refresh" }).click();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await page.getByLabel("Search work").fill("no-such-synthetic-case");
  await expect(page.getByText("No work matches these filters.")).toBeVisible();
});

test("shows loading and empty receipt states and preserves a draft on stale case conflict", async ({
  page,
  request,
}, info) => {
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/intakes", async (route) => {
    await gate;
    await route.fulfill({ json: { items: [] } });
  });
  await page.goto("/?view=intake");
  await expect(page.getByText("Loading receipts…")).toBeVisible();
  await page.screenshot({ path: info.outputPath("intake-loading.png") });
  release();
  await expect(
    page.getByText("No deliveries yet. Upload a file to begin."),
  ).toBeVisible();
  await page.screenshot({ path: info.outputPath("intake-empty.png") });
  await page.unroute("**/api/intakes");
  const source = `conflict-${info.project.name}`;
  const bytes =
    "record_id,npi,provider_name,address,city,state,zip,phone,location_id,reference_phone\nC,1234567890,Synthetic Conflict,1 Example Street,Boston,MA,02108,6175550100,C,6175550199\n";
  const receipt = await (
    await request.post(
      `/api/intakes/files?filename=synthetic.csv&source=${source}`,
      { data: bytes },
    )
  ).json();
  await request.post(`/api/intakes/${receipt.id}/commit`, {
    data: {
      actor: "Synthetic Reviewer",
      reason: "Conflict setup",
      policy: "valid_rows",
      expected_attempt: receipt.attempt_id,
    },
  });
  const all = await (await request.get("/api/work")).json();
  const item = all.items.find((c: { source: string }) => c.source === source);
  await page.goto(`/?view=work&case=${item.id}`);
  await page
    .getByRole("combobox", { name: "Action", exact: true })
    .selectOption("triage");
  await page.getByLabel("actor *", { exact: true }).fill("Draft Reviewer");
  await page
    .getByLabel("reason *", { exact: true })
    .fill("Keep this unsaved reason");
  await request.post(`/api/work/${item.id}/events`, {
    data: {
      action: "assign",
      actor: "Other local reviewer",
      reason: "Concurrent ownership",
      owner: "Morgan",
      expected_version: 0,
    },
  });
  await page.getByRole("button", { name: "Save review event" }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Case changed since it was opened",
  );
  await expect(page.getByLabel("reason *", { exact: true })).toHaveValue(
    "Keep this unsaved reason",
  );
  await page.getByRole("button", { name: "Retry / refresh" }).click();
  await expect(page.getByText("correction · version 1")).toBeVisible();
  await expect(page.getByLabel("reason *", { exact: true })).toHaveValue(
    "Keep this unsaved reason",
  );
  await page.screenshot({
    path: info.outputPath("intake-conflict-draft.png"),
    fullPage: true,
  });
});
