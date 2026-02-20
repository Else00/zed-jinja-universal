// === PURE GO (no jinja) ===
package main

import (
    "fmt"
    "strings"
)

type User struct {
    Name  string
    Email string
    Age   int
}

func (u *User) Greet() string {
    return fmt.Sprintf("Hello, %s!", u.Name)
}

func ProcessUsers(users []User) []string {
    var results []string
    for _, user := range users {
        if user.Age >= 18 {
            results = append(results, user.Greet())
        }
    }
    return results
}
