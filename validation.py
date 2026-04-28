def password_validation(password):
    upper = 0
    lower = 0
    digit = 0
    special = 0

    for i in password:
        if i.islower():
            lower += 1
        elif i.isupper():
            upper += 1
        elif i.isdigit():
            digit += 1
        elif not i.isalnum():
            special += 1

    return lower >= 1 and upper >= 1 and digit >= 1 and special >= 1 and len(password) >= 8


def valid_email(email):
    return "@" in email and "." in email