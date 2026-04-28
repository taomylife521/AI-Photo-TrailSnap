---
outline: [2, 3]
---

# TrailSnap CLI

::: tip
TrailSnap CLI is a command-line tool built on TrailSnap APIs. It can be used directly in your terminal, or as a Skill for Agents.
:::

## Install

Choose one method:

### pip

```bash
pip install trailsnap-cli
trailsnap -v
```

### npm

```bash
npm install -g trailsnap-cli
trailsnap -v
```

### Binary release

Download from GitHub Releases and add it to your PATH:  
https://github.com/LC044/TrailSnap/releases

## Configure

Before using API commands, configure your API URL and token (see [Token Settings](/en/docs/guide/settings/tokensetting)):

```bash
trailsnap config set --url <url> --token <token>
```

Verify:

```bash
trailsnap photos list --limit 5
```

## Common commands

- List photos: `trailsnap photos list --limit 20`
- View photo info: `trailsnap photos info --photo-id <id>`
- List albums: `trailsnap albums list`
- List tags: `trailsnap tags list`

For the full command list:

```bash
trailsnap --help
```
