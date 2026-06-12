# Kiro Ambassador Application Form — Reference

## URL
https://kiro.dev/ambassadors/apply/

## Form Framework
React Hook Form (RHF) + Next.js Server Actions

## Conditional Required Field Pitfall

The form contains `discordUsername`, a **required field that is hidden by default**.
It only appears in the DOM when `isDiscordMember` is set to `"yes"`. If left on
`"no"` or unset, RHF still validates it internally (it stays in the `_fields`
registry with `{ required: true }`), producing a silent validation failure with
**no visible error message** and `isSubmitting: False`.

### Detection
Submit button shows no errors, URL does not change, `page.wait_for_navigation`
times out. The form appears "stuck".

### RHF Internal State Extraction

Trick to dump every field (including hidden ones) and their current errors:

```javascript
// Quick: stringified field values stored on the form element
const values = JSON.parse(
  document.querySelector('form')._valueTracker.getValue()
);
console.log(values);

// Deep: walk the React fiber to the RHF control object
const formEl = document.querySelector('form');
const fiberKey = Object.keys(formEl).find(k => k.startsWith('__reactFiber$'));
const fiber = formEl[fiberKey];
const control = fiber.return.memoizedProps.control;
console.log(control._fields);           // field registry (hidden + visible)
console.log(control._formState.fieldErrors);  // validation errors
console.log(control._fieldValues);      // current values object
console.log(control._formState.isSubmitting);
```

### Key Fields

- `name` — text, required
- `email` — email, required
- `country` — select, required
- `isDiscordMember` — radio yes/no, required
- `discordUsername` — text, required, **appears only when isDiscordMember=yes**
- `company` — text, required
- `jobTitle` — text, required
- `socialProfile` — url
- `githubProfile` — url
- `kiroUserId` — text
- `kiroUsageDuration` — select, required
- `kiroExperience` — textarea, required
- `contentBackground` — textarea, required
- `communityEngagement` — textarea, required
- `programGoals` — textarea, required
- `interestedActivities` — checkbox group, required

### Working Playwright Flow

```python
# 1. Set isDiscordMember = "yes" to reveal discordUsername
page.locator('input[value="yes"]').check()   # or label-based locator

# 2. Fill discordUsername (any plausible username)
page.locator('input[name="discordUsername"]').fill('username123')

# 3. Fill remaining required fields
# 4. Submit
```

## Email Infrastructure

Domain: `antisecta.com` — catch-all forwards all mail to `Alex.bayov.fake@gmail.com`
Pattern: `{letter}.bayov@antisecta.com` tracked in `/root/.hermes/antisecta_email_tracker.json`
