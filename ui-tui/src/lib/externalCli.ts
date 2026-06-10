import { spawn } from 'node:child_process'



export interface LaunchResult {

  code: null | number

  error?: string

}



const resolveClawksisBin = () => process.env.CLAWK_BIN?.trim() || 'clawk'



export const launchClawksisCommand = (args: string[]): Promise<LaunchResult> =>

  new Promise(resolve => {

    const child = spawn(resolveClawksisBin(), args, { stdio: 'inherit' })



    child.on('error', err => resolve({ code: null, error: err.message }))

    child.on('exit', code => resolve({ code }))

  })

