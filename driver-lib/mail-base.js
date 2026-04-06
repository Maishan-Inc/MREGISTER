class BaseMailProvider {
  constructor(config = {}) {
    this.config = config;
    this.verbose = config.verbose !== false;
    this._usedCodes = new Set();
  }

  _log(message) {
    if (this.verbose) {
      console.log(`  [Mail] ${message}`);
    }
  }

  async init() {}

  async createAddress() {
    return null;
  }

  async waitForCode(_email, _timeout = 600, _otpSentAt = Date.now()) {
    throw new Error('waitForCode is not implemented');
  }

  async close() {}
}

module.exports = { BaseMailProvider };
