// === PURE JAVASCRIPT (no jinja) ===
const API_URL = "https://api.example.com";

class UserService {
    constructor(baseUrl) {
        this.baseUrl = baseUrl;
        this.cache = new Map();
    }

    async fetchUser(id) {
        if (this.cache.has(id)) {
            return this.cache.get(id);
        }
        const response = await fetch(`${this.baseUrl}/users/${id}`);
        const user = await response.json();
        this.cache.set(id, user);
        return user;
    }
}

function formatDate(date) {
    const options = { year: 'numeric', month: 'long', day: 'numeric' };
    return new Date(date).toLocaleDateString('en-US', options);
}
