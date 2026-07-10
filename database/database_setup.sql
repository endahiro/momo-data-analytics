-- =====================================================================
-- MoMo SMS Data Analytics — Database Setup Script
-- Target: MySQL 8.0+
-- Purpose: Create schema, constraints, indexes, and sample data for the
--          MoMo mobile money transaction analytics system.
-- =====================================================================

DROP DATABASE IF EXISTS momo_analytics;
CREATE DATABASE momo_analytics
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;
USE momo_analytics;


-- =====================================================================
-- 1. USERS
--    Any person who appears in an SMS as sender or receiver. We
--    normalize this so a person's name/phone is stored once, not
--    repeated on every transaction.
-- =====================================================================
CREATE TABLE users (
    user_id        INT           NOT NULL AUTO_INCREMENT,
    full_name      VARCHAR(100)  NOT NULL                  COMMENT 'Person name as parsed from the SMS body',
    phone_number   VARCHAR(20)   DEFAULT NULL              COMMENT 'MSISDN e.g. 250788XXXXXX; nullable — some SMS mask it',
    account_code   VARCHAR(20)   DEFAULT NULL              COMMENT 'Short account/agent code that follows some payee names',
    is_account_owner BOOLEAN     NOT NULL DEFAULT FALSE    COMMENT 'TRUE for the phone owner whose SMS were exported',
    created_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id),
    UNIQUE KEY uq_users_phone (phone_number),
    CONSTRAINT chk_users_phone_format
        CHECK (phone_number IS NULL OR phone_number REGEXP '^[0-9*+]+$')
) ENGINE=InnoDB COMMENT='People appearing as senders or receivers in MoMo SMS records';


-- =====================================================================
-- 2. TRANSACTION_CATEGORIES
--    Fixed lookup of the transaction types we identified in the XML:
--    Incoming Money, Bank Deposit, Transfer to Mobile, Payment to Code
--    Holder, Airtime Purchase, Direct Payment (Merchant), Withdrawal,
--    Internet/Bundle.
-- =====================================================================
CREATE TABLE transaction_categories (
    category_id     INT           NOT NULL AUTO_INCREMENT,
    category_name   VARCHAR(50)   NOT NULL                 COMMENT 'Short label used in reports and dashboards',
    description     VARCHAR(255)  DEFAULT NULL             COMMENT 'What kinds of SMS map to this category',
    direction       ENUM('CREDIT','DEBIT','NEUTRAL') NOT NULL
                                                             COMMENT 'CREDIT = money in, DEBIT = money out, NEUTRAL = OTP/system',

    PRIMARY KEY (category_id),
    UNIQUE KEY uq_category_name (category_name)
) ENGINE=InnoDB COMMENT='Business classification for each transaction';


-- =====================================================================
-- 3. TRANSACTIONS
--    Main fact table — one row per parsed SMS message. Uses the
--    Financial Transaction Id from the SMS body as a natural key
--    where available, otherwise a synthetic id.
-- =====================================================================
CREATE TABLE transactions (
    transaction_id      BIGINT         NOT NULL AUTO_INCREMENT,
    external_tx_id      VARCHAR(50)    DEFAULT NULL          COMMENT 'Financial Transaction Id / TxId parsed from SMS body',
    category_id         INT            NOT NULL              COMMENT 'FK to transaction_categories',
    sender_id           INT            DEFAULT NULL          COMMENT 'FK to users; NULL for deposits/system events',
    receiver_id         INT            DEFAULT NULL          COMMENT 'FK to users; NULL for withdrawals',
    amount              DECIMAL(15,2)  NOT NULL              COMMENT 'Transaction amount in RWF',
    fee                 DECIMAL(15,2)  NOT NULL DEFAULT 0    COMMENT 'Fee charged by MoMo, in RWF',
    new_balance         DECIMAL(15,2)  DEFAULT NULL          COMMENT 'Account balance after the transaction, in RWF',
    tx_datetime         DATETIME       NOT NULL              COMMENT 'When the transaction occurred (parsed from body)',
    sms_received_at     DATETIME       DEFAULT NULL          COMMENT 'When the confirmation SMS was received',
    raw_body            TEXT           DEFAULT NULL          COMMENT 'Original SMS body; kept for audit/debugging',
    created_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (transaction_id),
    UNIQUE KEY uq_external_tx_id (external_tx_id),

    CONSTRAINT fk_tx_category  FOREIGN KEY (category_id) REFERENCES transaction_categories(category_id),
    CONSTRAINT fk_tx_sender    FOREIGN KEY (sender_id)   REFERENCES users(user_id)  ON DELETE SET NULL,
    CONSTRAINT fk_tx_receiver  FOREIGN KEY (receiver_id) REFERENCES users(user_id)  ON DELETE SET NULL,

    CONSTRAINT chk_tx_amount_positive CHECK (amount >  0),
    CONSTRAINT chk_tx_fee_nonneg      CHECK (fee    >= 0),
    CONSTRAINT chk_tx_balance_nonneg  CHECK (new_balance IS NULL OR new_balance >= 0)
) ENGINE=InnoDB COMMENT='Main fact table: one row per parsed MoMo SMS transaction';

-- Enforce "sender and receiver must differ" via triggers (portable across
-- MySQL 8.x and MariaDB — some versions don't allow column-vs-column
-- comparisons inside a table-level CHECK constraint).
DELIMITER $$
CREATE TRIGGER trg_tx_parties_differ_bi
BEFORE INSERT ON transactions
FOR EACH ROW
BEGIN
    IF NEW.sender_id IS NOT NULL
       AND NEW.receiver_id IS NOT NULL
       AND NEW.sender_id = NEW.receiver_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Sender and receiver must be different users';
    END IF;
END$$

CREATE TRIGGER trg_tx_parties_differ_bu
BEFORE UPDATE ON transactions
FOR EACH ROW
BEGIN
    IF NEW.sender_id IS NOT NULL
       AND NEW.receiver_id IS NOT NULL
       AND NEW.sender_id = NEW.receiver_id THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Sender and receiver must be different users';
    END IF;
END$$
DELIMITER ;

-- Indexes for the queries the dashboard will actually run
CREATE INDEX idx_tx_datetime   ON transactions (tx_datetime);
CREATE INDEX idx_tx_category   ON transactions (category_id);
CREATE INDEX idx_tx_sender     ON transactions (sender_id);
CREATE INDEX idx_tx_receiver   ON transactions (receiver_id);
CREATE INDEX idx_tx_amount     ON transactions (amount);


-- =====================================================================
-- 4. TAGS
--    Free-form labels the analyst can apply to transactions
--    (e.g. "high_value", "recurring", "review", "suspicious").
-- =====================================================================
CREATE TABLE tags (
    tag_id     INT          NOT NULL AUTO_INCREMENT,
    tag_name   VARCHAR(50)  NOT NULL,
    tag_color  VARCHAR(7)   DEFAULT NULL   COMMENT 'Optional hex color for the dashboard UI',

    PRIMARY KEY (tag_id),
    UNIQUE KEY uq_tag_name (tag_name),
    CONSTRAINT chk_tag_color_hex CHECK (tag_color IS NULL OR tag_color REGEXP '^#[0-9A-Fa-f]{6}$')
) ENGINE=InnoDB COMMENT='Analyst-defined labels for tagging transactions';


-- =====================================================================
-- 5. TRANSACTION_TAGS  (junction table — resolves the many-to-many
--    relationship between transactions and tags)
--    A transaction can carry several tags; a tag can be applied to
--    many transactions.
-- =====================================================================
CREATE TABLE transaction_tags (
    transaction_id  BIGINT   NOT NULL,
    tag_id          INT      NOT NULL,
    applied_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_by      VARCHAR(50) DEFAULT 'system'   COMMENT 'User or rule that applied this tag',

    PRIMARY KEY (transaction_id, tag_id),
    CONSTRAINT fk_tt_transaction FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id) ON DELETE CASCADE,
    CONSTRAINT fk_tt_tag         FOREIGN KEY (tag_id)         REFERENCES tags(tag_id)                 ON DELETE CASCADE
) ENGINE=InnoDB COMMENT='M:N junction between transactions and tags';


-- =====================================================================
-- 6. SYSTEM_LOGS
--    Structured log of ETL activity: what was parsed, what was
--    skipped, and why. Optional link to a transaction when the log
--    entry relates to a specific record.
-- =====================================================================
CREATE TABLE system_logs (
    log_id           BIGINT        NOT NULL AUTO_INCREMENT,
    transaction_id   BIGINT        DEFAULT NULL       COMMENT 'FK to transactions; NULL for general/system events',
    log_level        ENUM('INFO','WARNING','ERROR','DEBUG') NOT NULL DEFAULT 'INFO',
    source           VARCHAR(50)   NOT NULL           COMMENT 'ETL component that emitted the log (parser, cleaner, loader)',
    message          VARCHAR(500)  NOT NULL,
    logged_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (log_id),
    CONSTRAINT fk_log_transaction FOREIGN KEY (transaction_id)
        REFERENCES transactions(transaction_id) ON DELETE SET NULL
) ENGINE=InnoDB COMMENT='ETL and processing logs, optionally linked to a transaction';

CREATE INDEX idx_log_level    ON system_logs (log_level);
CREATE INDEX idx_log_logged   ON system_logs (logged_at);


-- =====================================================================
-- SAMPLE DATA (DML)
-- =====================================================================

-- ---- Categories (the fixed set derived from the XML) --------------------
INSERT INTO transaction_categories (category_name, direction, description) VALUES
    ('Incoming Money',           'CREDIT',  'Funds received from another mobile money user'),
    ('Bank Deposit',             'CREDIT',  'Cash deposit added to the mobile money account'),
    ('Transfer to Mobile',       'DEBIT',   'Peer-to-peer transfer to another mobile number'),
    ('Payment to Code Holder',   'DEBIT',   'Payment to a merchant identified by a short code'),
    ('Airtime Purchase',         'DEBIT',   'Purchase of airtime credit via *162#'),
    ('Direct Payment',           'DEBIT',   'Merchant direct debit (e.g. utility, subscription)'),
    ('Withdrawal',               'DEBIT',   'Cash-out at an agent'),
    ('Internet Bundle',          'DEBIT',   'Purchase of a data/internet bundle');

-- ---- Users --------------------------------------------------------------
INSERT INTO users (full_name, phone_number, account_code, is_account_owner) VALUES
    ('Account Owner',   '250788110381', '36521838', TRUE),
    ('Jane Smith',      '250791666666', NULL,       FALSE),
    ('Samuel Carter',   '250790777777', NULL,       FALSE),
    ('Alex Doe',        '250789888888', NULL,       FALSE),
    ('Robert Brown',    '250788999999', NULL,       FALSE),
    ('Linda Green',     '250795963036', NULL,       FALSE),
    ('DIRECT PAYMENT LTD', NULL,        '47842929', FALSE);

-- ---- Transactions (real samples parsed from the provided XML) ----------
INSERT INTO transactions
    (external_tx_id, category_id, sender_id, receiver_id, amount, fee, new_balance, tx_datetime, sms_received_at, raw_body)
VALUES
    ('76662021700', 1, 2, 1, 2000.00,   0.00, 2000.00,  '2024-05-10 16:30:51', '2024-05-10 16:30:58',
        'You have received 2000 RWF from Jane Smith (*********013) on your mobile money account at 2024-05-10 16:30:51.'),
    ('73214484437', 4, 1, 2, 1000.00,   0.00, 1000.00,  '2024-05-10 16:31:39', '2024-05-10 16:31:46',
        'TxId: 73214484437. Your payment of 1,000 RWF to Jane Smith 12845 has been completed at 2024-05-10 16:31:39.'),
    (NULL,          2, NULL, 1, 40000.00, 0.00, 40400.00, '2024-05-11 18:43:49', '2024-05-11 18:45:36',
        'A bank deposit of 40000 RWF has been added to your mobile money account at 2024-05-11 18:43:49.'),
    (NULL,          3, 1, 3, 10000.00, 100.00, 28300.00, '2024-05-11 20:34:47', '2024-05-11 20:34:55',
        '10000 RWF transferred to Samuel Carter (250791666666) from 36521838 at 2024-05-11 20:34:47.'),
    ('13913173274', 5, 1, NULL, 2000.00, 0.00, 25280.00, '2024-05-12 11:41:28', '2024-05-12 11:41:35',
        'Your payment of 2000 RWF to Airtime with token has been completed at 2024-05-12 11:41:28.'),
    ('13947831685', 6, 1, 7, 25000.00, 0.00, 4060.00,   '2024-05-14 21:01:00', '2024-05-14 21:01:09',
        'A transaction of 25000 RWF by DIRECT PAYMENT LTD on your MOMO account was successfully completed.');

-- ---- Tags ---------------------------------------------------------------
INSERT INTO tags (tag_name, tag_color) VALUES
    ('high_value',   '#E24B4A'),
    ('recurring',    '#378ADD'),
    ('needs_review', '#EF9F27'),
    ('merchant',     '#7F77DD'),
    ('personal',     '#1D9E75');

-- ---- Transaction_Tags (M:N in action) ----------------------------------
INSERT INTO transaction_tags (transaction_id, tag_id, applied_by) VALUES
    (3, 1, 'rule:amount>10000'),
    (4, 1, 'rule:amount>10000'),
    (6, 1, 'rule:amount>10000'),
    (2, 5, 'system'),
    (4, 5, 'system'),
    (6, 4, 'system'),
    (5, 2, 'analyst'),
    (6, 3, 'analyst');

-- ---- System Logs -------------------------------------------------------
INSERT INTO system_logs (transaction_id, log_level, source, message) VALUES
    (NULL, 'INFO',    'parser',  'ETL run started for modified_sms_v2.xml (1691 records found)'),
    (1,    'INFO',    'cleaner', 'Successfully parsed incoming money transaction'),
    (NULL, 'WARNING', 'parser',  'Skipped 40 non-transaction messages (OTP/system notifications)'),
    (3,    'INFO',    'loader',  'Bank deposit inserted; sender is external (NULL)'),
    (6,    'WARNING', 'cleaner', 'Merchant name normalized from "DIRECT PAYMENT LTD  " (trailing whitespace)'),
    (NULL, 'ERROR',   'parser',  'Malformed date field in raw record; entry sent to dead-letter queue');


-- =====================================================================
-- SAMPLE QUERIES — used for CRUD testing and dashboard prototypes
-- =====================================================================

-- Q1: All transactions with human-readable category and party names
SELECT  t.transaction_id,
        c.category_name,
        s.full_name  AS sender,
        r.full_name  AS receiver,
        t.amount,
        t.fee,
        t.tx_datetime
FROM    transactions t
JOIN    transaction_categories c ON c.category_id = t.category_id
LEFT JOIN users s ON s.user_id = t.sender_id
LEFT JOIN users r ON r.user_id = t.receiver_id
ORDER BY t.tx_datetime;

-- Q2: Total volume per category (for the dashboard pie chart)
SELECT  c.category_name,
        COUNT(*)        AS tx_count,
        SUM(t.amount)   AS total_amount,
        AVG(t.amount)   AS avg_amount
FROM    transactions t
JOIN    transaction_categories c ON c.category_id = t.category_id
GROUP BY c.category_name
ORDER BY total_amount DESC;

-- Q3: Transactions flagged as high value (demonstrates the M:N join)
SELECT  t.transaction_id,
        t.amount,
        GROUP_CONCAT(tg.tag_name ORDER BY tg.tag_name SEPARATOR ', ') AS tags
FROM    transactions t
JOIN    transaction_tags tt ON tt.transaction_id = t.transaction_id
JOIN    tags tg              ON tg.tag_id         = tt.tag_id
GROUP BY t.transaction_id, t.amount
HAVING  FIND_IN_SET('high_value', REPLACE(GROUP_CONCAT(tg.tag_name), ' ', '')) > 0
ORDER BY t.amount DESC;

-- Q4: Recent ETL warnings and errors from the logs
SELECT  log_id, log_level, source, message, logged_at
FROM    system_logs
WHERE   log_level IN ('WARNING','ERROR')
ORDER BY logged_at DESC
LIMIT 10;

-- Q5: A CRUD demonstration — safe UPDATE + safe DELETE
UPDATE transactions
SET    new_balance = 27300.00
WHERE  transaction_id = 4;

DELETE FROM transaction_tags
WHERE  transaction_id = 5 AND tag_id = 2;
