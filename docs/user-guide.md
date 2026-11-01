# CodeGuard — User Guide

## 1. Create an account and sign in

1. Open CodeGuard and choose **Create an account**.
2. Enter a username, an email address (used for password resets) and a password of at least 10 characters that is not too common or entirely numeric.
3. You are signed in straight away with the default role chosen by your administrator, normally **Analyst**.
4. Use **Sign in** on later visits. You land on your start page (the Overview unless you change it in Settings > Display). **Forgot your password?** sends a reset link by email; locally, the email appears in the terminal running the server.
5. Sign out from the account menu (your initials, top right), or from Settings > Sessions.

Roles:

- **Viewers** can browse and read shared reports.
- **Analysts** can also run simulations and manage their own scenarios.
- **Administrators** can also manage shared scenarios and user roles.

## Finding your way around

The sidebar groups CodeGuard the way an analysis usually flows:

- **Overview**: key figures, the average residual risk, your next actions and where compromises land.
- **Model**: **Supply chain** (the five stages, their assets, controls and history), **Threat library** and **Security controls**.
- **Simulate**: **Simulations** (start a run) and **Results** (every completed run).
- **Analyze and respond**: **Risk analysis** (trends, exposure by stage, the effect of controls, comparisons) and **Remediation**.
- **Records**: **Reports** (the archive, exports and printable documents) and **Activity and audit**.

The bar at the top shows where you are (breadcrumbs), a light/dark switch, your **notifications** and the account menu. On a phone, the menu button opens the sidebar.

## 2. Explore the supply chain and the threat library

**Supply chain** shows the five stages in order. Open a stage to see its assets, the controls that protect it, the scenarios that start there, how a compromise can reach and leave it, and its recent outcomes across simulations. The graph aggregates every propagation path defined by the scenarios you can see.


**Threat library** lists the scenarios you can see.

- Search by text, or filter by entry stage, severity, status and visibility.
- **Shared** scenarios (including the six *Seeded* ones) are visible to everyone. **Private** scenarios are visible only to you.

Open a scenario to see:

- its **propagation graph**, where arcs above the stages skip stages and arcs below point backwards;
- each rule's probability and rationale;
- assumptions, business impact and affected assets;
- the security controls relevant to it.

To build your own scenario, either click **Clone as private** and then **Edit**, or choose **New scenario**. Rules must start from the initial stage or from a stage reachable from it.

## 3. Run a simulation

1. Open **Simulations** and choose a scenario (they are grouped by where the attack starts), or use **New simulation** in the top bar, or **Simulate** on a scenario.
2. The configuration has four steps; use **Next** and **Back** to move between them.
   1. **Scenario**: the one you picked (you can load a different one).
   2. **Inputs**: likelihood, severity, impact and threshold are filled in from the scenario. Changes apply to this run only.
   3. **Controls**: tick the security controls in place, grouped as preventive, detective and recovery. *Select scenario-relevant* ticks the controls linked to the scenario; *Clear* removes them all. Tip: run once with **no controls** first, to see the unprotected picture.
   4. **Review and run**: check the summary and click **Run simulation**. You are taken to the result.

## 4. Interpret the results

A result opens on its **Summary** tab: inherent and residual risk, a plain-language account of what happened, the propagation diagram, the top recommendations and the **affected assets** (what an attacker could reach at each compromised stage). The other tabs hold the detail: **Stage analysis**, **Propagation paths** (every edge decision), **Controls and recommendations**, and **Inputs and method**. Charts can be hovered or focused with the keyboard for exact values, and each has a **Show as a table** link.

- **Inherent risk** is the overall risk with no controls. **Residual risk** is the risk with your enabled controls. Both are on a 0–100 scale.
  - Classes: Low < 15, Moderate < 30, High < 50, Critical ≥ 50.
  - The overall score is a weighted average of the five stage risks, with Production weighted highest.
- **The supply chain diagram** shows each stage's state, using a symbol and a text label as well as colour:
  - ▶ **Entry point**: where the attack starts (compromised by assumption).
  - ✖ **Compromised**: an edge into the stage met the threshold.
  - ⊘ **Blocked**: the edge would have propagated, but your controls pushed it below the threshold.
  - △ **Exposed**: the attack reached the stage, but the edge was below the threshold even without controls.
  - ✓ **Unaffected**: no modeled path reached the stage.
- **Edges** use line styles as well as colour: solid red means propagated, dashed green with ✕ means blocked, dotted amber means below threshold, and faint dotted means not evaluated.
- **Stage cards** list the likelihood, coverage, risk and a sentence explaining the result.
- **Propagation paths evaluated** lists every edge decision with its arithmetic.
- **What happened, in plain language** summarises the outcome.
- **Charts** show the overall risk, the risk by stage, and the propagation outcomes. Each chart has a text alternative, and the same numbers appear in the tables.

## 5. Improve with mitigations

**Recommended controls** are ranked by how much they would lower the overall residual risk *in this model*. Each one shows:

- the stages it protects;
- the propagation paths it affects (for example, "IDE → Version Control: 85% → 34%");
- the exact modeled change (for example, 26.6 → 4.4);
- its effort and priority.

To try a recommendation:

1. Click **Rerun with changes**. The form is pre-filled with the same inputs.
2. Tick the recommended controls and run again.
3. On the new report, click **Compare with previous run** to see before and after side by side: the change in risk, which stages changed state, and which controls were added.

The **Control effectiveness summary** shows how much each enabled control contributes, measured by removing it and re-running.

### Plan the remediation

Analysts can turn a recommendation into tracked work:

1. On a report, click **Add to plan** next to a recommended control. The item records the report, the residual risk at that time and the modeled reduction.
2. Open **Remediation** in the sidebar. Filter by status, prioritise by due date or by modeled reduction, open an item, and set its status (Open, In progress, Done, Risk accepted), a due date and notes such as the owner or a ticket reference.
3. When the control is in place, re-run the same scenario with it enabled. The item then shows **Confirmed by run …** with the before and after risk. Until then it says **Not re-run yet**.

Remediation items are private to you, like your reports. Every change is recorded in the audit log. Each control's catalog page explains why its effectiveness value was chosen and what it does not cover.

## 6. Review reports

- **Reports** lists your past runs (tabs: yours, shared, everything you can see). You can filter them, open them, export one or all as CSV, or open a run as a **report document**, laid out for printing or saving as PDF.
- **Results** shows completed runs as cards with each stage's outcome at a glance.
- **Risk analysis** compares inherent and residual risk across runs, shows which stages carry the most exposure and which controls remove the most risk, and lets you compare any two runs.
- Each report keeps the exact scenario version and inputs it was run with. If the scenario is edited or deleted later, the report shows a notice but its numbers never change.
- **Share report** makes a report visible read-only to every user (for example, to Viewers). **Make private** reverses this.
- **Export CSV** downloads a report's stages and edge decisions.
- **Activity and audit** shows your own recorded actions as a timeline or a table. Administrators see everyone's actions.
- **Notifications** (the bell) collects reports colleagues share, remediation items due within 7 days or overdue, and security events on your account such as a password change, a role change or failed sign-ins.

## 7. Settings

Open **Settings** from the account menu or the sidebar. Every setting is saved to your account.

- **Profile** and **Account**: your name, job title and team; your email address (changing it asks for your password).
- **Appearance and theme**: light, dark or match your device; **Paper** (warm), **Pearl** (cool white) or **Sage** (pearl white with a green-grey cast) surfaces; and an accent theme (Ultramarine, Iris or Graphite). The sun/moon button in the top bar switches light and dark and saves the choice here.
- **Text and typography**: text size and the heading typeface.
- **Display**: comfortable or compact density, relative or absolute timestamps, rows per page and the page you land on after signing in.
- **Accessibility**: reduce motion, increase contrast, always underline links.
- **Notifications**: which categories appear in your inbox.
- **Privacy and data**: share new reports with everyone by default (off unless you turn it on), and **Download my data** as a JSON file.
- **Password and security**: change your password and review recent sign-ins and failed attempts.
- **Sessions**: details of this session and **Sign out of all other sessions**.
- Administrators also see **Organization** (deployment policies, read-only because they are set by environment variables) and **Users and roles**.

## 8. Limitations to keep in mind

- The scenarios are hypothetical, and the probabilities and control effectiveness values are illustrative.
- Decisions use a fixed threshold. They are a simplified model, not a forecast.
- Controls are assumed to act independently. Each control's stated assumptions and limitations are on its catalog page.
- A verified remediation item means the *model* confirms the reduction, not that the control works in your environment.
- A modeled improvement does not guarantee the same protection in a real organisation. CodeGuard is a teaching tool, not a security assessment.
