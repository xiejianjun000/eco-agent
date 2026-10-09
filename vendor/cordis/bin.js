#!/usr/bin/env node

import { Context } from '@eco-agent/cordis'
import { pathToFileURL } from 'node:url'
import Loader from '@eco-agent/cordis-plugin-loader'

const ctx = new Context()
ctx.baseUrl = pathToFileURL(process.cwd()).href + '/'

await ctx.plugin(Loader)
await ctx.loader.create({
  name: '@eco-agent/cordis-plugin-include',
  config: {
    path: './cordis.yml',
  },
})
