-- === PURE SQL (no jinja) ===
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON users(email);

INSERT INTO users (username, email) VALUES
    ('john_doe', 'john@example.com'),
    ('jane_doe', 'jane@example.com');

SELECT 
    u.id,
    u.username,
    COUNT(o.id) as order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE u.created_at > '2024-01-01'
GROUP BY u.id, u.username
HAVING COUNT(o.id) > 5
ORDER BY order_count DESC;
