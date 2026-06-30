variable "name" {
  description = "Nombre global y unico del bucket de GCS."
  type        = string
}

variable "project" {
  description = "ID del proyecto de GCP donde se crea el bucket."
  type        = string
}

variable "location" {
  description = "Region del bucket (region simple = mas barato que multi-region)."
  type        = string
  default     = "europe-southwest1"
}

variable "storage_class" {
  description = "Clase de almacenamiento por defecto del bucket."
  type        = string
  default     = "STANDARD"
}

variable "default_kms_key_name" {
  description = "Nombre completo de la clave KMS usada como CMEK por defecto del bucket."
  type        = string
}

variable "versioning" {
  description = "Versionado de objetos. Apagado por defecto: versionar duplica almacenamiento y coste."
  type        = bool
  default     = false
}

variable "force_destroy" {
  description = "Permite a Terraform borrar el bucket aunque contenga objetos. true solo en dev."
  type        = bool
  default     = false
}

variable "lifecycle_rules" {
  description = "Reglas de ciclo de vida para abaratar el almacenamiento (transiciones de clase o borrado por antiguedad)."
  type = list(object({
    action_type   = string           # "SetStorageClass" o "Delete"
    storage_class = optional(string) # requerido si action_type = SetStorageClass
    age           = number           # antiguedad del objeto en dias
  }))
  default = []
}

variable "labels" {
  description = "Etiquetas para clasificar el bucket (proyecto, capa, entorno)."
  type        = map(string)
  default     = {}
}
