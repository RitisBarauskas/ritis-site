variable "project_id" {
  description = "The Google Cloud project behind Firebase Hosting."
  type        = string
  default     = "ritis-dev"
}

variable "region" {
  description = "Cloud Run, Firestore and the image registry; in the EU, as the privacy policy states."
  type        = string
  default     = "europe-west1"
}

variable "billing_account" {
  description = "The billing account the project is on (Blaze): the budget alert is set on it."
  type        = string
}

variable "budget_amount" {
  description = "Monthly budget in the billing account's currency; alerts at 50, 90 and 100 percent."
  type        = number
}

variable "api_image" {
  description = "The API image to run, from this project's registry, by digest."
  type        = string
}

variable "site_url" {
  description = "Where the site is served; the API is reached on the same origin through Hosting."
  type        = string
  default     = "https://ritis-dev.web.app"
}

variable "flitt_merchant_id" {
  description = "Flitt merchant; 1549901 is Flitt's public test merchant."
  type        = number
  default     = 1549901
}

variable "telegram_chat_id" {
  description = "The owner's chat with the site's bot, where notices go."
  type        = number
}
