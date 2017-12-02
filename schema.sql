-- TODO: this

CREATE TABLE IF NOT EXISTS currency_users (
    user_id BIGINT PRIMARY KEY,
    coins INT DEFAULT 0,
    last_picked TIMESTAMP,

    CONSTRAINT no_debt_please CHECK (coins >= 0)
);
